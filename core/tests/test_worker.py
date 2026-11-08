import json
import pytest
from fakeredis.aioredis import FakeRedis
from brz.config import Settings
from brz.form_schema import FORM_REVISION
from brz.models import CodePlan
from brz.presets import BY_ID
from brz.sandbox import RunResult
from brz.store import Store, task_record
from brz.worker import Coordinator


class NeverAI:
    async def structured(self, *args, **kwargs):
        pytest.fail("Preset invoked model planning")
    async def call(self, *args, **kwargs):
        pytest.fail("Preset invoked model summary")


class FakeAI:
    async def structured(self, ctx, *args, **kwargs):
        ctx.calls += 1
        return CodePlan(code="print(42)")
    async def call(self, ctx, *args, **kwargs):
        ctx.calls += 1
        return "Evidence summary"


class FixtureRunner:
    """Application contract double; never evidence of actual containment."""
    def __init__(self, outcome="succeeded", syntax=False):
        self.outcome, self.syntax, self.runs = outcome, syntax, 0
    def run_code(self, code, upload, emit, cancelled):
        self.runs += 1
        text = "SyntaxError: test fixture\n" if self.syntax else "fixture output\n"
        emit("stdout", {"text": text})
        return RunResult(self.outcome, text, error="fixture error" if self.outcome != "succeeded" else "")
    def run_browser(self, plan, emit, cancelled):
        self.runs += 1
        return RunResult("succeeded", details={"receipt": {"id": "forged"}})


async def setup_task(pattern="code", source="preset", request=None, runner=None, ai=None):
    settings = Settings()
    store = Store(settings, FakeRedis(decode_responses=True))
    task = task_record("owner", pattern, source, request or {"kind": "preset", "preset_id": "csv-analysis"}, "ip")
    await store.enqueue(task)
    coordinator = Coordinator(settings, store, runner or FixtureRunner(), ai or NeverAI())
    return store, task, coordinator


async def test_preset_uses_sandbox_but_zero_model_calls():
    store, task, coordinator = await setup_task()
    await coordinator.process(task["id"])
    state = await store.task(task["id"])
    assert state["status"] == "succeeded"
    assert state["source"] == "preset" and state["provider_requests"] == 0
    assert state["usage"] == [] and coordinator.runner.runs == 1
    events = await store.redis.xrange("events:" + task["id"])
    assert any(json.loads(fields["event"])["type"] == "stdout" for _, fields in events)


@pytest.mark.parametrize("outcome", ["blocked", "timed_out", "oom_killed", "output_limit", "infrastructure_error"])
async def test_policy_or_resource_failure_never_repairs(outcome):
    runner = FixtureRunner(outcome)
    store, task, coordinator = await setup_task(source="live_ai", request={"kind": "task", "prompt": "test", "pattern": "code"}, runner=runner, ai=FakeAI())
    await coordinator.process(task["id"])
    state = await store.task(task["id"])
    assert state["status"] == outcome and runner.runs == 1
    assert state["provider_requests"] == 1 and state["recoveries"] == 0


async def test_code_error_has_at_most_two_additional_attempts():
    runner = FixtureRunner("failed", syntax=True)
    store, task, coordinator = await setup_task(source="live_ai", request={"kind": "task", "prompt": "test", "pattern": "code"}, runner=runner, ai=FakeAI())
    await coordinator.process(task["id"])
    state = await store.task(task["id"])
    assert state["status"] == "failed"
    assert runner.runs == 3 and state["recoveries"] == 2 and state["provider_requests"] == 3


async def test_cancelled_queue_item_never_launches_container():
    store, task, coordinator = await setup_task()
    await store.redis.set("cancel:" + task["id"], "1")
    await coordinator.process(task["id"])
    assert (await store.task(task["id"]))["status"] == "cancelled"
    assert coordinator.runner.runs == 0


async def test_browser_receipt_is_not_trusted_without_form_service_record():
    store, original, coordinator = await setup_task(pattern="browser")
    action = await store.prepare_action(original, "Title", "Message", "/screenshot.png")
    submit_id = await store.approve(action["id"], "owner", "ip")
    await coordinator.process(submit_id)
    state = await store.task(submit_id)
    assert state["status"] == "failed"
    assert "trusted submission receipt" in state["error"]
    assert await store.receipt(action["id"]) is None


async def test_preparation_creates_pending_action_without_submission():
    class FormRunner(FixtureRunner):
        def run_browser(self, plan, emit, cancelled):
            self.runs += 1
            return RunResult("succeeded", artifacts={"screenshot.png": b"\x89PNG\r\n\x1a\nfixture"}, details={
                "form_revision": FORM_REVISION, "form_fields": {"title": plan["title"], "message": plan["message"]}})
    store, task, coordinator = await setup_task(pattern="browser", request={"kind": "preset", "preset_id": "demo-form"}, runner=FormRunner())
    await coordinator.process(task["id"])
    state = await store.task(task["id"])
    assert state["status"] == "awaiting_approval" and state["pending_action"]["screenshot_url"]
    action = json.loads(await store.redis.get("action:" + state["pending_action"]["id"]))
    assert action["status"] == "pending" and "permit_hash" not in action
    assert await store.receipt(action["id"]) is None
