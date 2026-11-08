"""Exercise state boundaries against Redis semantics without a live daemon."""
import asyncio
import hashlib
import json
import time

import fakeredis.aioredis
import pytest

from brz import store as store_module
from brz.config import Settings
from brz.errors import ControlError
from brz.form_schema import FORM_REVISION
from brz.models import SubmitRequest
from brz.store import Store, encode, task_record


@pytest.fixture
async def store():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    instance = Store(Settings(), redis=client)
    yield instance
    await instance.close()


def assert_control(error, reason, status=None):
    # Assertions use stable structured reasons rather than human error wording.
    assert isinstance(error, ControlError)
    assert error.reason == reason
    if status is not None:
        assert error.status == status


async def test_destination_change_before_approval_requires_new_preparation(store):
    from dataclasses import replace
    task = task_record('owner', 'browser', 'preset', {}, 'ip')
    await store.enqueue(task)
    action = await store.prepare_action(task, 'Title', 'Message', '/screenshot.png')
    store.settings = replace(store.settings, demo_url='https://changed.example.com:8443')
    with pytest.raises(ControlError) as error:
        await store.approve(action['id'], 'owner', 'ip')
    assert_control(error.value, 'destination_changed', 409)


async def test_destination_change_before_commit_rejects_existing_permit(store):
    from dataclasses import replace
    task = task_record('owner', 'browser', 'preset', {}, 'ip')
    await store.enqueue(task)
    action = await store.prepare_action(task, 'Title', 'Message', '/screenshot.png')
    submit_id = await store.approve(action['id'], 'owner', 'ip')
    plan = (await store.task(submit_id))['input']['plan']
    store.settings = replace(store.settings, demo_url='https://changed.example.com:8443')
    request = SubmitRequest(**{k:plan[k] for k in ('action_id','permit','title','message','revision')})
    with pytest.raises(ControlError) as error:
        await store.submit(request)
    assert_control(error.value, 'destination_changed', 409)


async def pending_action(store, owner="session-a"):
    task = task_record(owner, "browser", "preset", {"kind": "preset", "preset_id": "demo-form"}, "ip-a")
    await store.enqueue(task)
    assert await store.redis.lpop("queue") == task["id"]
    await store.update(task["id"], status="awaiting_approval")
    action = await store.prepare_action(task, "A reviewed title", "Only create a demo receipt.", "/screenshot.png")
    return task, action


async def approved_request(store):
    task, action = await pending_action(store)
    submit_task_id = await store.approve(action["id"], task["owner"], "ip-a")
    submit_task = await store.task(submit_task_id)
    plan = submit_task["input"]["plan"]
    request = SubmitRequest(**{key: plan[key] for key in SubmitRequest.model_fields})
    return action, request


async def test_concurrent_fixed_window_limit_and_expiring_counter(store):
    results = await asyncio.gather(
        *(store.rate("start", "one-ip", limit=6, window=60, now=120.5) for _ in range(20)),
        return_exceptions=True,
    )
    assert sum(result is None for result in results) == 6
    denied = [result for result in results if isinstance(result, Exception)]
    assert len(denied) == 14
    for error in denied:
        assert_control(error, "rate_limited", 429)
        assert error.retry_after > 0
    key = "rate:start:one-ip:2"
    assert await store.redis.get(key) == "20"
    assert 0 < await store.redis.ttl(key) <= 61

    # A new fixed bucket has an independent allowance; old buckets expire.
    await store.rate("start", "one-ip", limit=6, window=60, now=180.5)
    assert await store.redis.get("rate:start:one-ip:3") == "1"
    await store.redis.pexpire(key, 1)
    await asyncio.sleep(0.01)
    assert not await store.redis.exists(key)


async def test_rate_namespaces_and_subjects_are_independent(store):
    await store.rate("start", "ip-a", limit=1, window=60, now=1)
    await store.rate("start", "ip-b", limit=1, window=60, now=1)
    await store.rate("model", "ip-a", limit=1, window=60, now=1)
    with pytest.raises(ControlError) as error:
        await store.rate("start", "ip-a", limit=1, window=60, now=1)
    assert_control(error.value, "rate_limited", 429)


async def test_concurrent_queue_admission_never_exceeds_eight(store):
    tasks = [task_record("session-a", "code", "custom_code", {"kind": "code"}, "ip-a") for _ in range(24)]
    results = await asyncio.gather(*(store.enqueue(task) for task in tasks), return_exceptions=True)
    accepted = [result for result in results if isinstance(result, dict)]
    denied = [result for result in results if isinstance(result, Exception)]
    assert len(accepted) == 8
    assert len(denied) == 16
    assert await store.redis.llen("queue") == 8
    assert len(set(await store.redis.lrange("queue", 0, -1))) == 8
    for error in denied:
        assert isinstance(error, ControlError)
        assert error.reason in {"queue_full", "queue_busy"}
    # Rejected tasks must not leave readable task records behind.
    accepted_ids = {task["id"] for task in accepted}
    for task in tasks:
        assert bool(await store.task(task["id"])) == (task["id"] in accepted_ids)


async def test_task_access_requires_the_owning_session(store):
    task = task_record("session-a", "code", "custom_code", {"kind": "code"}, "ip-a")
    await store.enqueue(task)
    assert (await store.owned_task(task["id"], "session-a"))["id"] == task["id"]
    for owner, task_id in [("session-b", task["id"]), ("session-a", "0" * 32)]:
        with pytest.raises(ControlError) as error:
            await store.owned_task(task_id, owner)
        assert_control(error.value, "not_found", 404)


async def test_upload_and_artifact_blobs_are_owner_and_task_bound(store):
    upload = await store.blob("session-a", b"a,b\n1,2\n", "input.csv", "text/csv")
    _, content = await store.get_blob(upload["upload_id"], "session-a")
    assert content == b"a,b\n1,2\n"
    artifact = await store.blob("session-a", b'{"rows":1}', "analysis.json", "application/json", task_id="task-a")
    _, content = await store.get_blob(artifact["id"], "session-a", "task-a")
    assert content == b'{"rows":1}'
    for blob_id, owner, task_id in [
        (upload["upload_id"], "session-b", None),
        (upload["upload_id"], "session-a", "task-a"),
        (artifact["id"], "session-b", "task-a"),
        (artifact["id"], "session-a", "task-b"),
        (artifact["id"], "session-a", None),
    ]:
        with pytest.raises(ControlError) as error:
            await store.get_blob(blob_id, owner, task_id)
        assert_control(error.value, "not_found", 404)
    assert 0 < await store.redis.ttl(f"blob:{artifact['id']}") <= 900


async def test_blob_size_limits_apply_before_storage(store):
    for content, task_id in [(b"x" * (2 * 1024 * 1024 + 1), None), (b"x" * (8 * 1024 * 1024 + 1), "task-a")]:
        with pytest.raises(ControlError) as error:
            await store.blob("session-a", content, "oversized.csv", "text/csv", task_id)
        assert_control(error.value, "file_too_large", 413)
    assert not await store.redis.keys("blob:*")


async def test_session_reuse_preserves_csrf_and_unknown_session_creates_new(store):
    sid, csrf = await store.session(None)
    assert len(sid) == len(csrf) == 64
    assert await store.session(sid) == (sid, csrf)
    new_sid, new_csrf = await store.session("0" * 64)
    assert new_sid != sid
    assert new_csrf != csrf
    with pytest.raises(ControlError) as error:
        await store.require_session("not-a-session")
    assert_control(error.value, "session_required", 401)


async def test_pending_action_cannot_be_submitted_without_approval(store):
    _, action = await pending_action(store)
    request = SubmitRequest(action_id=action["id"], permit="x" * 43,
                            title=action["title"], message=action["message"], revision=action["revision"])
    with pytest.raises(ControlError) as error:
        await store.submit(request)
    assert_control(error.value, "approval_required", 403)
    assert await store.receipt(action["id"]) is None


async def test_approval_is_session_owned_and_missing_action_is_not_disclosed(store):
    _, action = await pending_action(store)
    for action_id, owner in [(action["id"], "session-b"), ("0" * 32, "session-a")]:
        with pytest.raises(ControlError) as error:
            await store.approve(action_id, owner, "ip-b")
        assert_control(error.value, "not_found", 404)
    saved = json.loads(await store.redis.get(f"action:{action['id']}"))
    assert saved["status"] == "pending"
    assert "permit_hash" not in saved


async def test_approval_checks_logical_expiry_as_well_as_redis_ttl(store):
    _, action = await pending_action(store)
    key = f"action:{action['id']}"
    saved = json.loads(await store.redis.get(key))
    saved["expires_at"] = time.time() - 1
    await store.redis.set(key, encode(saved), ex=300)
    with pytest.raises(ControlError) as error:
        await store.approve(action["id"], "session-a", "ip-a")
    assert_control(error.value, "approval_expired", 409)
    await store.redis.delete(key)
    with pytest.raises(ControlError) as error:
        await store.approve(action["id"], "session-a", "ip-a")
    assert_control(error.value, "not_found", 404)


async def test_form_revision_change_prevents_approval(store, monkeypatch):
    _, action = await pending_action(store)
    monkeypatch.setattr(store_module, "FORM_REVISION", "changed-form-revision")
    with pytest.raises(ControlError) as error:
        await store.approve(action["id"], "session-a", "ip-a")
    assert_control(error.value, "form_changed", 409)
    assert await store.redis.llen("queue") == 0


async def test_full_queue_leaves_approval_pending(store):
    _, action = await pending_action(store)
    for _ in range(8):
        await store.enqueue(task_record("another-session", "code", "preset", {}, "other-ip"))
    with pytest.raises(ControlError) as error:
        await store.approve(action["id"], "session-a", "ip-a")
    assert_control(error.value, "queue_full", 429)
    saved = json.loads(await store.redis.get(f"action:{action['id']}"))
    assert saved["status"] == "pending"
    assert "permit_hash" not in saved


async def test_concurrent_approval_creates_exactly_one_submission_task(store):
    _, action = await pending_action(store)
    ids = await asyncio.gather(*(store.approve(action["id"], "session-a", "ip-a") for _ in range(8)))
    assert len(set(ids)) == 1
    assert await store.redis.lrange("queue", 0, -1) == [ids[0]]
    task = await store.task(ids[0])
    plan = task["input"]["plan"]
    assert plan["kind"] == "submit_form"
    assert plan["title"] == action["title"]
    assert plan["message"] == action["message"]
    assert plan["url"] == store.settings.demo_url
    saved = json.loads(await store.redis.get(f"action:{action['id']}"))
    assert saved["permit_hash"] == hashlib.sha256(plan["permit"].encode()).hexdigest()
    assert "permit" not in saved


@pytest.mark.parametrize("field,value,reason", [
    ("permit", "incorrect-permit-" * 3, "invalid_permit"),
    ("title", "Changed after approval", "payload_changed"),
    ("message", "A different side effect", "payload_changed"),
    ("revision", "changed-form-revision", "form_changed"),
])
async def test_submission_rejects_tampered_capability_or_payload(store, field, value, reason):
    action, request = await approved_request(store)
    modified = request.model_copy(update={field: value})
    with pytest.raises(ControlError) as error:
        await store.submit(modified)
    assert_control(error.value, reason)
    assert await store.receipt(action["id"]) is None


async def test_current_form_revision_is_rechecked_at_submission(store, monkeypatch):
    action, request = await approved_request(store)
    monkeypatch.setattr(store_module, "FORM_REVISION", "different-current-revision")
    with pytest.raises(ControlError) as error:
        await store.submit(request)
    assert_control(error.value, "form_changed", 409)
    assert await store.receipt(action["id"]) is None


async def test_approved_action_expiry_blocks_effect(store):
    action, request = await approved_request(store)
    key = f"action:{action['id']}"
    saved = json.loads(await store.redis.get(key))
    saved["expires_at"] = time.time() - 1
    await store.redis.set(key, encode(saved), ex=300)
    with pytest.raises(ControlError) as error:
        await store.submit(request)
    assert_control(error.value, "approval_required", 403)
    assert await store.receipt(action["id"]) is None


async def test_concurrent_submission_commits_one_receipt_and_replays_safely(store):
    action, request = await approved_request(store)
    receipts = await asyncio.gather(*(store.submit(request) for _ in range(8)))
    assert len({receipt["id"] for receipt in receipts}) == 1
    receipt = receipts[0]
    assert receipt["effect"] == "demo_record_only"
    assert receipt["title"] == request.title
    assert receipt["message"] == request.message
    assert receipt["revision"] == FORM_REVISION
    assert len(await store.redis.keys("receipt:*")) == 1
    assert await store.receipt(action["id"]) == receipt
    # A lost response can be reconciled even after the action key disappears.
    await store.redis.delete(f"action:{action['id']}")
    assert await store.submit(request) == receipt
    for field, value in [("permit", "wrong-" * 8), ("title", "An altered replay"), ("message", "Changed replay")]:
        with pytest.raises(ControlError) as error:
            await store.submit(request.model_copy(update={field: value}))
        assert_control(error.value, "invalid_permit", 403)
    assert await store.receipt(action["id"]) == receipt
