"""Dedicated form origin: no control-plane routes and no external side effects."""
from contextlib import asynccontextmanager
from html import escape
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from redis.exceptions import RedisError
from .config import Settings
from .errors import ControlError
from .form_schema import DISCLOSURE, FORM_REVISION
from .models import SubmitRequest
from .store import Store


def create_form_app(settings=None, store=None):
    settings = settings or Settings.from_env()
    store = store or Store(settings)
    @asynccontextmanager
    async def lifespan(app):
        yield
        await store.close()
    app = FastAPI(title="BRZ Demo Form", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(ControlError)
    async def controlled(request, exc):
        return JSONResponse({"detail": {"reason": exc.reason, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RedisError)
    async def unavailable(request, exc):
        return JSONResponse({"detail": "Form state unavailable; no submission accepted."}, status_code=503)

    @app.get("/", response_class=HTMLResponse)
    async def form():
        return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="brz-form-revision" content="{FORM_REVISION}"><title>BRZ · Demo Request</title>
<style>body{{background:#101615;color:#e3ece7;font:17px system-ui;max-width:640px;margin:70px auto;padding:24px}}small{{color:#7eddac}}h1{{font-size:38px}}label{{display:block;margin:24px 0 8px}}input,textarea{{box-sizing:border-box;width:100%;padding:14px;background:#1c2622;border:1px solid #41594c;border-radius:8px;color:inherit;font:inherit}}textarea{{height:130px}}button{{margin-top:24px;border:0;border-radius:8px;background:#b8f879;padding:14px 24px;color:#122016;font-weight:700}}p{{color:#a4b8ad;line-height:1.6}}</style></head>
<body><small>BLAST RADIUS ZERO / CONTROLLED ACTION</small><h1>Demo Request</h1><p>{DISCLOSURE}</p>
<form id="demo-form" method="post" action="/submit"><label for="title">Title</label><input id="title" name="title" maxlength="120" required>
<label for="message">Message</label><textarea id="message" name="message" maxlength="2000"></textarea>
<input type="hidden" name="permit"><input type="hidden" name="action_id"><input type="hidden" name="revision" value="{FORM_REVISION}">
<button type="submit">Create demo receipt</button></form><p>Submission requires a valid, single-use approval permit from the dashboard.</p></body></html>''', headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'", "X-Content-Type-Options": "nosniff"})

    @app.post("/submit")
    async def submit(request: Request):
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 16384:
                raise ControlError("request_too_large", "Form submission is too large.", 413)
            chunks.append(chunk)
        body = b"".join(chunks)
        try:
            if request.headers.get("content-type", "").startswith("application/json"):
                payload = SubmitRequest.model_validate_json(body)
            else:
                # Reject duplicate fields rather than allowing parser-specific overrides.
                from urllib.parse import parse_qsl
                if not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
                    raise ValueError("Unsupported form encoding")
                pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=8)
                if len(pairs) != len(dict(pairs)):
                    raise ValueError("Duplicate fields")
                payload = SubmitRequest.model_validate(dict(pairs))
        except (ValidationError, ValueError):
            raise ControlError("invalid_form", "Submission fields are invalid.", 422) from None
        receipt = await store.submit(payload)
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(receipt)
        return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Demo receipt</title></head><body><h1>Demo receipt created</h1><pre id="receipt">{escape(json.dumps(receipt))}</pre><p>{DISCLOSURE}</p></body></html>''', headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'", "X-Content-Type-Options": "nosniff"})
    return app


app = create_form_app()
