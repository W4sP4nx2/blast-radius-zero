import json
import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from brz.ai import CallContext, ModelClient
from brz.config import Settings
from brz.errors import ControlError
from brz.models import CodePlan
from brz.store import Store


def client(handler, **changes):
    settings = Settings(ai_enabled=True, vultr_api_key="test-only", vultr_text_model="test-model", **changes)
    store = Store(settings, FakeRedis(decode_responses=True))
    model = ModelClient(settings, store, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    model.models_verified = True
    return model


def success(text='{"code":"print(42)"}', finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": finish}],
                                     "usage": {"prompt_tokens": 12, "completion_tokens": 8}})


async def test_code_ceiling_usage_and_no_hidden_retries():
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        return success()
    model = client(handler)
    ctx = CallContext("task")
    plan = await model.structured(ctx, "schema", "user", CodePlan, "code")
    assert plan.code == "print(42)"
    assert len(bodies) == ctx.calls == 1
    assert bodies[0]["max_tokens"] == 2048
    assert ctx.usage[0]["tokens"]["completion_tokens"] == 8
    await model.close()


async def test_invalid_json_uses_only_two_recoveries():
    model = client(lambda request: success("not JSON"))
    ctx = CallContext("task")
    with pytest.raises(ControlError, match="valid bounded JSON"):
        await model.structured(ctx, "schema", "user", CodePlan)
    assert ctx.calls == 3 and ctx.recoveries == 2
    await model.close()


async def test_generated_code_is_repaired_at_utf8_byte_boundary():
    code = "#" + "é" * 32767 + "\n"
    replies = iter([
        json.dumps({"code": code + "é"}),
        json.dumps({"code": " \n "}),
        json.dumps({"code": code}),
    ])
    model = client(lambda request: success(next(replies)))
    ctx = CallContext("task")
    plan = await model.structured(ctx, "schema", "user", CodePlan, "code")
    assert plan.code == code and len(plan.code.encode("utf-8")) == 65536
    assert ctx.calls == 3 and ctx.recoveries == 2
    await model.close()


async def test_truncated_json_is_retried_boundedly():
    model = client(lambda request: success("{}", "length"))
    ctx = CallContext("task")
    with pytest.raises(ControlError) as error:
        await model.structured(ctx, "schema", "user", CodePlan)
    assert error.value.reason == "model_truncated"
    assert ctx.calls == 3 and ctx.recoveries == 2
    await model.close()


async def test_five_failures_open_circuit_and_only_one_probe():
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(500)
    model = client(handler)
    for index in range(2):
        with pytest.raises(ControlError):
            await model.call(CallContext(str(index)), [])
    assert count == 5
    state = await model.state()
    assert not state["available"] and 0 < state["retry_after"] <= 60
    await model.store.redis.delete(model.key("open"))
    assert await model._before() is True
    with pytest.raises(ControlError) as error:
        await model._before()
    assert error.value.reason == "circuit_probe"
    await model._success()
    assert (await model.state())["available"]
    assert not await model.store.redis.exists(model.key("needs_probe"))
    await model.close()


async def test_invalid_credentials_disable_without_retry():
    model = client(lambda request: httpx.Response(401))
    ctx = CallContext("task")
    with pytest.raises(ControlError) as error:
        await model.call(ctx, [])
    assert error.value.reason == "invalid_credentials"
    assert ctx.calls == 1 and ctx.recoveries == 0
    assert not (await model.state())["available"]
    assert not await model.store.redis.exists(model.key("failures"))
    await model.close()


async def test_provider_retry_after_does_not_count_as_outage():
    model = client(lambda request: httpx.Response(429, headers={"Retry-After": "95"}))
    ctx = CallContext("task")
    with pytest.raises(ControlError) as error:
        await model.call(ctx, [])
    assert error.value.retry_after == 95
    assert ctx.calls == 1 and ctx.recoveries == 0
    assert not await model.store.redis.exists(model.key("failures"))
    assert (await model.state())["retry_after"] > 0
    await model.close()


async def test_rate_limit_is_separate_from_provider_health():
    model = client(lambda request: success(), provider_per_minute=1)
    await model.call(CallContext("one"), [])
    ctx = CallContext("two")
    with pytest.raises(ControlError) as error:
        await model.call(ctx, [])
    assert error.value.reason == "rate_limited" and ctx.calls == 0
    assert (await model.state())["available"]
    await model.close()


async def test_five_call_cap_does_not_make_sixth_http_request():
    model = client(lambda request: pytest.fail("sixth request"))
    with pytest.raises(ControlError) as error:
        await model.call(CallContext("task", calls=5), [])
    assert error.value.reason == "model_call_limit"
    await model.close()


async def test_catalog_is_counted_and_unknown_models_fail_closed():
    model = client(lambda request: httpx.Response(200, json={"data": [{"id": "another-model"}]}))
    model.models_verified = False
    ctx = CallContext("task")
    with pytest.raises(ControlError) as error:
        await model.call(ctx, [])
    assert error.value.reason == "unknown_model"
    assert ctx.calls == 1
    await model.close()


async def test_disabled_ai_makes_no_http_requests():
    settings = Settings(ai_enabled=False)
    store = Store(settings, FakeRedis(decode_responses=True))
    model = ModelClient(settings, store, httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("HTTP called"))))
    with pytest.raises(ControlError) as error:
        await model.call(CallContext("task"), [])
    assert error.value.reason == "ai_unavailable"
    await model.close()
