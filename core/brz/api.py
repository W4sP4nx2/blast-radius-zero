import asyncio
from collections import deque
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import re
import time
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from redis.exceptions import RedisError
from .ai import ModelClient
from .config import Settings, TERMINAL
from .errors import ControlError
from .models import ExecuteRequest
from .presets import BY_ID, preset_ids, public_presets
from .store import Store, task_record

ID = r"^[a-f0-9]{32}$"


class BodyLimit:
    """Reject chunked as well as Content-Length bodies before parsing uploads/JSON."""
    def __init__(self, app, maximum=3 * 1024 * 1024):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        size = 0
        messages = deque()
        while True:
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.maximum:
                response = JSONResponse({"detail": ControlError("request_too_large", "Request body exceeds 3 MiB.", 413).detail()}, status_code=413)
                return await response(scope, receive, send)
            messages.append(message)
            if message["type"] == "http.disconnect" or not message.get("more_body", False):
                break
        async def bounded_receive():
            return messages.popleft() if messages else await receive()
        await self.app(scope, bounded_receive, send)


def create_app(settings=None, store=None):
    settings = settings or Settings.from_env()
    store = store or Store(settings)
    ai = ModelClient(settings, store)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await ai.close()
        await store.close()

    app = FastAPI(title="Blast Radius Zero", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.settings, app.state.ai = store, settings, ai
    app.add_middleware(BodyLimit)

    @app.exception_handler(ControlError)
    async def controlled(request, exc):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else {}
        return JSONResponse({"detail": exc.detail()}, status_code=exc.status, headers=headers)

    @app.exception_handler(RedisError)
    async def unavailable(request, exc):
        return JSONResponse({"detail": ControlError("state_unavailable", "Shared state is unavailable; execution is paused.", 503, 5).detail()}, status_code=503, headers={"Retry-After": "5"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        errors = exc.errors()
        message = errors[0].get("msg", "Invalid request") if errors else "Invalid request"
        return JSONResponse({"detail": ControlError("invalid_request", "Input validation failed: " + message, 422).detail()}, status_code=422)

    async def session(request: Request):
        sid = request.cookies.get("brz_session")
        await store.require_session(sid)
        return sid

    async def mutation(request: Request, sid=Depends(session)):
        state = await store.require_session(sid)
        supplied = request.headers.get("x-csrf-token", "")
        origin = request.headers.get("origin")
        if not supplied or not hmac.compare_digest(supplied, state["csrf"]) or (origin and origin != settings.app_origin):
            raise ControlError("csrf_rejected", "Session confirmation failed. Reload the page.", 403)
        return sid

    def client_key(request):
        # Uvicorn trusts forwarded addresses ONLY from Caddy's configured gateway.
        address = request.client.host if request.client else "unknown"
        return hashlib.sha256(address.encode()).hexdigest()[:32]

    async def readiness(pattern):
        raw = await store.redis.get("worker:heartbeat")
        status = json.loads(raw) if raw else {}
        if not status.get("ready"):
            raise ControlError("worker_unavailable", "The sandbox worker is unavailable. Check Docker and preflight.", 503, 10)
        if pattern == "browser" and not status.get("browser_ready"):
            raise ControlError("browser_unavailable", "Browser containment preflight has not passed.", 503, 10)

    @app.get("/api/session")
    async def establish_session(request: Request):
        await store.capacity()
        await store.rate("session", client_key(request), 30, 60)
        sid, csrf = await store.session(request.cookies.get("brz_session"))
        response = JSONResponse({"csrf_token": csrf})
        response.set_cookie("brz_session", sid, max_age=settings.session_ttl, secure=settings.secure_cookies,
                            httponly=True, samesite="strict", path="/")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    async def health():
        try:
            await store.ping()
            raw = await store.redis.get("worker:heartbeat")
            ready = json.loads(raw) if raw else {}
            ai_state = await ai.state()
            redis_ready = True
        except RedisError:
            ready, redis_ready = {}, False
            ai_state = {"enabled": settings.ai_enabled, "available": False, "reason": "Shared state unavailable"}
        return {"status": "healthy" if ready.get("ready") and redis_ready else "degraded",
                "sandbox_provider": ready.get("provider", settings.sandbox_runtime),
                "worker_ready": bool(ready.get("ready")), "browser_ready": bool(ready.get("browser_ready")),
                "redis_ready": redis_ready, "ai": ai_state,
                "limits": {"concurrent_sandboxes": 2, "concurrent_browsers": 1, "queue": settings.queue_limit,
                           "task_starts_per_minute": settings.starts_per_minute, "live_ai_tasks_per_hour": settings.ai_tasks_per_hour,
                           "provider_requests_per_minute": settings.provider_per_minute}}

    @app.get("/api/presets")
    async def presets():
        return {"presets": public_presets()}

    @app.post("/api/uploads", status_code=201)
    async def upload(request: Request, file: UploadFile = File(...), sid=Depends(mutation)):
        await store.capacity()
        await store.rate("uploads", client_key(request), 6, 60)
        if not (file.filename or "").lower().endswith(".csv"):
            raise ControlError("csv_required", "Upload a UTF-8 CSV file.", 422)
        content = await file.read(2 * 1024 * 1024 + 1)
        await file.close()
        if not content or len(content) > 2 * 1024 * 1024:
            raise ControlError("file_too_large", "CSV must contain data and be at most 2 MiB.", 413)
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ControlError("csv_encoding", "CSV must use UTF-8 encoding.", 422) from None
        if "\x00" in text:
            raise ControlError("csv_encoding", "Binary files are not accepted.", 422)
        # The caller's filename never becomes a filesystem path or archive member.
        name = re.sub(r"[^A-Za-z0-9_. -]", "_", file.filename or "input.csv")[-100:]
        return await store.blob(sid, content, name, "text/csv")

    @app.post("/api/execute", status_code=202)
    async def execute(payload: ExecuteRequest, request: Request, sid=Depends(mutation)):
        await store.capacity()
        key = client_key(request)
        await store.rate("task", key, settings.starts_per_minute, 60)
        data = payload.model_dump()
        if payload.kind == "preset":
            preset = BY_ID.get(payload.preset_id)
            if not preset:
                raise ControlError("unknown_preset", "Choose an available preset.", 422)
            pattern, source = preset["pattern"], "preset"
        else:
            pattern = "code" if payload.kind == "code" else payload.pattern
            source = "custom_code" if payload.kind == "code" else "live_ai"
        await readiness(pattern)
        if payload.upload_id:
            await store.get_blob(payload.upload_id, sid)
        if payload.kind == "task":
            state = await ai.state()
            if not state["available"]:
                raise ControlError("ai_unavailable", state["reason"], 503, state.get("retry_after", 0))
            await store.rate("live_ai", key, settings.ai_tasks_per_hour, 3600)
        task = await store.enqueue(task_record(sid, pattern, source, data, key))
        return {"task_id": task["id"]}

    @app.get("/api/tasks/{task_id}")
    async def task_status(task_id: str, sid=Depends(session)):
        task = await store.owned_task(task_id, sid)
        # Never expose internal plans, permits, session IDs or network configuration.
        public = {k: v for k, v in task.items() if k not in ("owner", "input", "ip_hash")}
        if public.get("pending_action"):
            action = public["pending_action"]
            public["pending_action"] = {**action, "expired": action["expires_at"] <= time.time()}
        return JSONResponse(public, headers={"Cache-Control": "no-store"})

    @app.get("/api/tasks/{task_id}/events")
    async def events(task_id: str, request: Request, sid=Depends(session)):
        await store.owned_task(task_id, sid)
        cursor = request.headers.get("last-event-id", "0-0")
        if not re.fullmatch(r"\d+-\d+", cursor):
            cursor = "0-0"
        async def stream():
            nonlocal cursor
            # Poll rather than unbounded XREAD connections: bounded, reconnectable SSE.
            while not await request.is_disconnected():
                records = await store.redis.xrange(f"events:{task_id}", min=f"({cursor}", count=100)
                for event_id, fields in records:
                    event = json.loads(fields["event"])
                    event["id"] = event_id
                    yield f"id: {event_id}\ndata: {json.dumps(event)}\n\n"
                    cursor = event_id
                task = await store.task(task_id)
                if not task or (task["status"] in TERMINAL and not records):
                    yield "event: end\ndata: {}\n\n"
                    break
                if not records:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.25 if records else 1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel(task_id: str, sid=Depends(mutation)):
        task = await store.owned_task(task_id, sid)
        if task["status"] not in TERMINAL:
            await store.redis.set(f"cancel:{task_id}", "1", ex=settings.task_ttl)
        return {"task_id": task_id, "cancel_requested": task["status"] not in TERMINAL}

    @app.get("/api/tasks/{task_id}/artifacts/{artifact_id}")
    async def artifact(task_id: str, artifact_id: str, sid=Depends(session)):
        await store.owned_task(task_id, sid)
        metadata, content = await store.get_blob(artifact_id, sid, task_id)
        filename = re.sub(r"[^A-Za-z0-9_.-]", "_", metadata["name"])
        disposition = "inline" if metadata["mime"] in ("image/png", "image/jpeg") else "attachment"
        return Response(content, media_type=metadata["mime"], headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                                                                   "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    @app.post("/api/actions/{action_id}/approve", status_code=202)
    async def approve(action_id: str, request: Request, sid=Depends(mutation)):
        await store.capacity()
        await readiness("browser")
        key = client_key(request)
        await store.rate("task", key, settings.starts_per_minute, 60)
        return {"task_id": await store.approve(action_id, sid, key)}

    return app


app = create_app()
