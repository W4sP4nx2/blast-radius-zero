"""Session-owned bounded Redis state. WATCH transactions guard admission and actions."""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from redis.asyncio import Redis
from redis.exceptions import WatchError
from .config import BROWSER_POLICY, CODE_POLICY, Settings
from .errors import ControlError
from .form_schema import FORM_REVISION, payload_hash


def encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def task_record(owner, pattern, source, request, ip_hash):
    now = time.time()
    return {"id": uuid.uuid4().hex, "owner": owner, "pattern": pattern, "source": source,
            "status": "queued", "created_at": now, "updated_at": now, "input": request,
            "ip_hash": ip_hash, "result": {}, "error": "", "summary": "", "artifacts": [],
            "usage": [], "policy": CODE_POLICY if pattern == "code" else BROWSER_POLICY}


class Store:
    def __init__(self, settings: Settings, redis=None):
        self.settings = settings
        self.redis = redis or Redis.from_url(settings.redis_url, decode_responses=True,
                                            socket_connect_timeout=3, socket_timeout=3)

    async def ping(self):
        return await self.redis.ping()

    async def close(self):
        await self.redis.aclose()

    async def capacity(self):
        info = await self.redis.info("memory")
        if int(info["used_memory"]) > self.settings.redis_high_water_bytes:
            raise ControlError("storage_capacity", "Temporary storage is full; try again after artifacts expire.", 503, 60)

    async def rate(self, namespace: str, subject: str, limit: int, window: int, now=None):
        now = time.time() if now is None else now
        bucket = int(now // window)
        key = f"rate:{namespace}:{subject}:{bucket}"
        async with self.redis.pipeline(transaction=True) as p:
            p.incr(key)
            p.expire(key, window + 1)
            count, _ = await p.execute()
        remaining = max(1, int((bucket + 1) * window - now))
        if count > limit:
            raise ControlError("rate_limited", "This request allowance is temporarily exhausted. Presets remain available within sandbox limits.", 429, remaining)

    async def session(self, session_id: str | None):
        if session_id and len(session_id) == 64:
            raw = await self.redis.get(f"session:{session_id}")
            if raw:
                await self.redis.expire(f"session:{session_id}", self.settings.session_ttl)
                return session_id, json.loads(raw)["csrf"]
        sid, csrf = secrets.token_hex(32), secrets.token_hex(32)
        await self.redis.set(f"session:{sid}", encode({"csrf": csrf}), ex=self.settings.session_ttl)
        return sid, csrf

    async def require_session(self, sid):
        raw = await self.redis.get(f"session:{sid}") if sid else None
        if not raw:
            raise ControlError("session_required", "Start a session before submitting a task.", 401)
        return json.loads(raw)

    async def enqueue(self, task):
        # Only the single execution coordinator consumes this bounded queue.
        for _ in range(10):
            async with self.redis.pipeline(transaction=True) as p:
                try:
                    await p.watch("queue")
                    if await p.llen("queue") >= self.settings.queue_limit:
                        raise ControlError("queue_full", "All waiting slots are occupied. Try again shortly.", 429, 10)
                    p.multi()
                    p.hset(f"task:{task['id']}", mapping={k: encode(v) for k, v in task.items()})
                    p.expire(f"task:{task['id']}", self.settings.task_ttl)
                    p.rpush("queue", task["id"])
                    await p.execute()
                    await self.event(task["id"], "status", {"status": "queued"})
                    return task
                except WatchError:
                    continue
        raise ControlError("queue_busy", "Task admission is busy; please retry.", 429, 2)

    async def task(self, task_id):
        raw = await self.redis.hgetall(f"task:{task_id}")
        return {k: json.loads(v) for k, v in raw.items()} if raw else None

    async def owned_task(self, task_id, owner):
        task = await self.task(task_id)
        if not task or not hmac.compare_digest(task["owner"], owner):
            raise ControlError("not_found", "Task not found or expired.", 404)
        return task

    async def update(self, task_id, **fields):
        key = f"task:{task_id}"
        if not await self.redis.exists(key):
            return
        fields["updated_at"] = time.time()
        await self.redis.hset(key, mapping={k: encode(v) for k, v in fields.items()})

    async def event(self, task_id, event_type, data):
        key = f"events:{task_id}"
        event = {"type": event_type, "data": data, "at": time.time()}
        event_id = await self.redis.xadd(key, {"event": encode(event)}, maxlen=512, approximate=False)
        await self.redis.expire(key, self.settings.task_ttl)
        return event_id

    async def status(self, task_id, status, **fields):
        await self.update(task_id, status=status, **fields)
        await self.event(task_id, "status", {"status": status})

    async def blob(self, owner, content: bytes, name: str, mime: str, task_id=None):
        if len(content) > (8 * 1024 * 1024 if task_id else 2 * 1024 * 1024):
            raise ControlError("file_too_large", "File exceeds its size limit.", 413)
        blob_id = uuid.uuid4().hex
        value = {"owner": owner, "name": name, "mime": mime, "task_id": task_id,
                 "body": base64.b64encode(content).decode()}
        await self.redis.set(f"blob:{blob_id}", encode(value), ex=self.settings.task_ttl)
        return {"id": blob_id, "name": name, "mime": mime,
                "url": f"/api/tasks/{task_id}/artifacts/{blob_id}"} if task_id else {"upload_id": blob_id, "name": name}

    async def get_blob(self, blob_id, owner, task_id=None):
        raw = await self.redis.get(f"blob:{blob_id}")
        blob = json.loads(raw) if raw else None
        if not blob or not hmac.compare_digest(blob["owner"], owner) or blob["task_id"] != task_id:
            raise ControlError("not_found", "File not found or expired.", 404)
        return blob, base64.b64decode(blob["body"])

    async def prepare_action(self, task, title, message, screenshot_url):
        aid = uuid.uuid4().hex
        action = {"id": aid, "owner": task["owner"], "task_id": task["id"], "source": task["source"],
                  "target": self.settings.demo_url,
                  "title": title, "message": message, "revision": FORM_REVISION,
                  "payload_hash": payload_hash(title, message, FORM_REVISION),
                  "screenshot_url": screenshot_url, "expires_at": time.time() + self.settings.approval_ttl,
                  "status": "pending"}
        await self.redis.set(f"action:{aid}", encode(action), ex=self.settings.approval_ttl)
        public = {k: v for k, v in action.items() if k not in ("owner", "payload_hash", "status", "source")}
        await self.update(task["id"], pending_action=public)
        await self.event(task["id"], "approval", public)
        return public

    async def approve(self, action_id, owner, ip_hash):
        key = f"action:{action_id}"
        for _ in range(10):
            async with self.redis.pipeline(transaction=True) as p:
                try:
                    await p.watch(key, "queue")
                    raw = await p.get(key)
                    action = json.loads(raw) if raw else None
                    if not action or not hmac.compare_digest(action["owner"], owner):
                        raise ControlError("not_found", "Approval not found or expired.", 404)
                    if action["expires_at"] <= time.time():
                        raise ControlError("approval_expired", "Prepare a new screenshot and approval.", 409)
                    if action["status"] != "pending":
                        if action.get("submit_task_id"):
                            return action["submit_task_id"]
                        raise ControlError("already_approved", "This action has already been approved.", 409)
                    if action["revision"] != FORM_REVISION:
                        raise ControlError("form_changed", "The form changed. Prepare it again before approving.", 409)
                    if action.get("target") != self.settings.demo_url:
                        raise ControlError("destination_changed", "The form destination changed. Prepare it again.", 409)
                    if await p.llen("queue") >= self.settings.queue_limit:
                        raise ControlError("queue_full", "No waiting slots. Approval remains pending.", 429, 10)
                    permit = secrets.token_urlsafe(32)
                    action["permit_hash"] = hashlib.sha256(permit.encode()).hexdigest()
                    action["status"] = "approved"
                    plan = {"kind": "submit_form", "url": action["target"],
                            "action_id": action_id, "permit": permit, "title": action["title"],
                            "message": action["message"], "revision": action["revision"]}
                    task = task_record(owner, "browser", action["source"], {"kind": "approved", "plan": plan}, ip_hash)
                    action["submit_task_id"] = task["id"]
                    p.multi()
                    p.set(key, encode(action), ex=max(1, int(action["expires_at"] - time.time())))
                    p.hset(f"task:{task['id']}", mapping={k: encode(v) for k, v in task.items()})
                    p.expire(f"task:{task['id']}", self.settings.task_ttl)
                    p.rpush("queue", task["id"])
                    await p.execute()
                    await self.event(task["id"], "status", {"status": "queued"})
                    return task["id"]
                except WatchError:
                    continue
        raise ControlError("approval_busy", "Approval is busy; please retry.", 429, 2)

    async def submit(self, request):
        """The effect and receipt live in one transaction; never trust browser claims."""
        key, receipt_key = f"action:{request.action_id}", f"receipt:{request.action_id}"
        digest = hashlib.sha256(request.permit.encode()).hexdigest()
        wanted = payload_hash(request.title, request.message, request.revision)
        for _ in range(10):
            async with self.redis.pipeline(transaction=True) as p:
                try:
                    await p.watch(key, receipt_key)
                    existing = await p.get(receipt_key)
                    if existing:
                        record = json.loads(existing)
                        if hmac.compare_digest(record["permit_hash"], digest) and hmac.compare_digest(record["payload_hash"], wanted):
                            return record["receipt"]
                        raise ControlError("invalid_permit", "Submission permit does not match.", 403)
                    raw = await p.get(key)
                    action = json.loads(raw) if raw else None
                    if not action or action["expires_at"] <= time.time() or action["status"] != "approved":
                        raise ControlError("approval_required", "An unexpired approval is required.", 403)
                    if not hmac.compare_digest(action.get("permit_hash", ""), digest):
                        raise ControlError("invalid_permit", "Submission permit does not match.", 403)
                    if request.revision != FORM_REVISION or action["revision"] != FORM_REVISION:
                        raise ControlError("form_changed", "The form changed. Prepare and approve again.", 409)
                    if action.get("target") != self.settings.demo_url:
                        raise ControlError("destination_changed", "The approved destination is no longer configured.", 409)
                    if not hmac.compare_digest(action["payload_hash"], wanted):
                        raise ControlError("payload_changed", "Approved field values cannot be changed.", 403)
                    receipt = {"id": uuid.uuid4().hex, "action_id": request.action_id,
                               "title": request.title, "message": request.message,
                               "submitted_at": time.time(), "revision": FORM_REVISION, "effect": "demo_record_only"}
                    receipt["target"] = action["target"]
                    record = {"permit_hash": digest, "payload_hash": wanted, "receipt": receipt}
                    action["status"] = "submitted"
                    p.multi()
                    p.set(receipt_key, encode(record), ex=3600)
                    p.set(key, encode(action), ex=3600)
                    await p.execute()
                    return receipt
                except WatchError:
                    continue
        raise ControlError("submission_busy", "Submission is busy; check the existing receipt.", 503, 2)

    async def receipt(self, action_id):
        raw = await self.redis.get(f"receipt:{action_id}")
        return json.loads(raw)["receipt"] if raw else None
