import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from brz.api import create_app
from brz.config import Settings
from brz.form_schema import FORM_REVISION
from brz.form_service import create_form_app
from brz.store import Store, task_record


@pytest.fixture
async def environment():
    settings = Settings()
    redis = FakeRedis(decode_responses=True)
    redis.info = AsyncMock(return_value={"used_memory": 1024})
    store = Store(settings, redis)
    app = create_app(settings, store)
    await redis.set("worker:heartbeat", json.dumps({"ready": True, "browser_ready": True}), ex=10)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:3000") as c:
        session = await c.get("/api/session")
        assert session.status_code == 200
        c.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        yield c, store, app
    await app.state.ai.close()
    await store.close()


async def test_presets_and_custom_code_admit_without_inference(environment):
    c, store, app = environment
    app.state.ai.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("Preset contacted provider")))
    response = await c.post("/api/execute", json={"kind": "preset", "preset_id": "csv-analysis"})
    assert response.status_code == 202
    state = (await c.get("/api/tasks/" + response.json()["task_id"])).json()
    assert state["source"] == "preset" and state["status"] == "queued"
    assert not {"owner", "input", "ip_hash"}.intersection(state)
    assert (await c.post("/api/execute", json={"kind": "code", "code_payload": "print(1)"})).status_code == 202


async def test_ai_disabled_returns_visible_preset_choices(environment):
    c, _, _ = environment
    response = await c.post("/api/execute", json={"kind": "task", "pattern": "code", "prompt": "analyze"})
    assert response.status_code == 503
    assert "csv-analysis" in response.json()["detail"]["available_presets"]
    assert response.json()["detail"]["reason"] == "ai_unavailable"


async def test_csrf_and_wrong_origin_rejected(environment):
    c, _, _ = environment
    payload = {"kind": "code", "code_payload": "print(1)"}
    assert (await c.post("/api/execute", json=payload, headers={"X-CSRF-Token": "wrong"})).status_code == 403
    assert (await c.post("/api/execute", json=payload, headers={"Origin": "https://evil.example"})).status_code == 403


async def test_caller_cannot_set_docker_parameters_or_large_code(environment):
    c, _, _ = environment
    payload = {"kind": "code", "code_payload": "print(1)", "network_mode": "host"}
    assert (await c.post("/api/execute", json=payload)).status_code == 422
    assert (await c.post("/api/execute", json={"kind": "code", "code_payload": "x" * 65537})).status_code == 422


async def test_cross_session_task_and_artifact_access_is_hidden(environment):
    c, store, app = environment
    response = await c.post("/api/execute", json={"kind": "preset", "preset_id": "csv-analysis"})
    task_id = response.json()["task_id"]
    sid = c.cookies.get("brz_session")
    artifact = await store.blob(sid, b"{}", "test.json", "application/json", task_id)
    assert (await c.get(artifact["url"])).status_code == 200
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:3000") as other:
        await other.get("/api/session")
        assert (await other.get("/api/tasks/" + task_id)).status_code == 404
        assert (await other.get(artifact["url"])).status_code == 404
        assert (await other.get(f"/api/tasks/{task_id}/events")).status_code == 404


async def test_upload_validation_and_owner_binding(environment):
    c, store, app = environment
    result = await c.post("/api/uploads", files={"file": ("sales.csv", b"x,y\n1,2\n", "text/csv")})
    assert result.status_code == 201
    assert (await c.post("/api/uploads", files={"file": ("evil.html", b"x", "text/html")})).status_code == 422
    assert (await c.post("/api/uploads", files={"file": ("huge.csv", b"x" * (2 * 1024 * 1024 + 1), "text/csv")})).status_code == 413
    c.cookies.clear()
    fresh = await c.get("/api/session")
    c.headers["X-CSRF-Token"] = fresh.json()["csrf_token"]
    response = await c.post("/api/execute", json={"kind": "preset", "preset_id": "csv-analysis", "upload_id": result.json()["upload_id"]})
    assert response.status_code == 404


async def test_sse_replay_and_cancel(environment):
    c, store, _ = environment
    response = await c.post("/api/execute", json={"kind": "code", "code_payload": "print(1)"})
    task_id = response.json()["task_id"]
    assert (await c.post(f"/api/tasks/{task_id}/cancel", json={})).status_code == 200
    assert await store.redis.exists(f"cancel:{task_id}")
    cursor = await store.event(task_id, "stdout", {"text": "first"})
    await store.event(task_id, "stdout", {"text": "second"})
    await store.status(task_id, "succeeded")
    response = await c.get(f"/api/tasks/{task_id}/events", headers={"Last-Event-ID": cursor})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "second" in response.text and "first" not in response.text


async def test_worker_and_storage_fail_closed(environment):
    c, store, _ = environment
    await store.redis.delete("worker:heartbeat")
    assert (await c.post("/api/execute", json={"kind": "preset", "preset_id": "csv-analysis"})).status_code == 503
    store.redis.info.return_value = {"used_memory": 999_999_999}
    assert (await c.post("/api/execute", json={"kind": "code", "code_payload": "print(1)"})).status_code == 503


async def test_form_endpoint_requires_permit_and_returns_trusted_receipt(environment):
    c, store, _ = environment
    sid = c.cookies.get("brz_session")
    task = task_record(sid, "browser", "preset", {}, "ip")
    await store.enqueue(task)
    action = await store.prepare_action(task, "Reviewed title", "Reviewed message", "/screenshot")
    response = await c.post(f"/api/actions/{action['id']}/approve", json={})
    assert response.status_code == 202
    submit_task = await store.task(response.json()["task_id"])
    internal = submit_task["input"]["plan"]
    payload = {k: internal[k] for k in ("action_id", "permit", "title", "message", "revision")}
    form = create_form_app(store.settings, store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=form), base_url="https://demo.example.com:8443", headers={"Accept": "application/json"}) as f:
        assert (await f.post("/submit", json={**payload, "permit": "x" * 43})).status_code == 403
        submitted = await f.post("/submit", json=payload)
        assert submitted.status_code == 200
        assert submitted.json()["effect"] == "demo_record_only"
        assert (await f.post("/submit", data=payload)).json()["id"] == submitted.json()["id"]
        assert (await f.post("/submit", json={**payload, "title": "Modified"})).status_code == 403
        page = await f.get("/")
        assert FORM_REVISION in page.text and 'id="demo-form"' in page.text


async def test_chunked_request_body_limit(environment):
    c, _, _ = environment
    async def body():
        for _ in range(4):
            yield b" " * 1024 * 1024
    response = await c.post("/api/execute", content=body(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


async def test_health_reports_administrator_selected_sandbox_provider(environment):
    client, _, _ = environment
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["sandbox_provider"] == "docker"
