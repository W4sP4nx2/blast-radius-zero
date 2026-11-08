"""UI contract checks using intercepted API responses, never simulated production runs.

Run against a local Next.js server with:
  BRZ_UI_URL=http://127.0.0.1:3300 python web/tests/workbench_e2e.py
Requires the Python playwright package and an installed Chromium browser.
"""

import base64
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

PRESETS = [
    {"id": "csv_analysis", "name": "CSV analysis", "description": "Aggregate a real CSV and return a downloadable summary.", "pattern": "code"},
    {"id": "network_denial", "name": "Test network containment", "description": "Attempt an external connection inside the offline sandbox.", "pattern": "code"},
    {"id": "timeout", "name": "Stop an infinite loop", "description": "Watch the execution deadline terminate a runaway task.", "pattern": "code"},
    {"id": "hn_research", "name": "Research with receipts", "description": "Capture the top Hacker News entries with sources and a screenshot.", "pattern": "browser"},
    {"id": "metadata_denial", "name": "Block cloud metadata", "description": "Attempt a metadata request through the trusted proxy.", "pattern": "browser"},
    {"id": "demo_form", "name": "Prepare a demo form", "description": "Inspect a filled form before explicitly approving submission.", "pattern": "browser"},
]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6c5sAAAAASUVORK5CYII=")


def main():
    base_url = os.environ.get("BRZ_UI_URL", "http://127.0.0.1:3300")
    with sync_playwright() as playwright:
        launch = {"headless": True}
        if os.environ.get("BRZ_CHROMIUM_EXECUTABLE"):
            launch["executable_path"] = os.environ["BRZ_CHROMIUM_EXECUTABLE"]
        browser = playwright.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        state = {"requests": [], "snapshots": {}, "mode": "code", "count": 0}

        def api(route):
            request = route.request
            path = request.url.split("/api/", 1)[1]
            state["requests"].append((request.method, path))
            if request.method == "POST":
                assert request.headers.get("x-csrf-token") == "test-csrf", path
            if path == "session":
                body = {"csrf_token": "test-csrf"}
            elif path == "health":
                body = {"status": "healthy", "worker_ready": True, "browser_ready": True, "ai": {"enabled": False, "available": False, "reason": "disabled"}}
            elif path == "presets":
                body = {"presets": PRESETS}
            elif path == "uploads":
                body = {"upload_id": "upload-1", "name": "sales.csv"}
            elif path == "execute":
                payload = request.post_data_json
                if payload["kind"] == "task":
                    route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": {"reason": "ai_disabled", "message": "Live AI unavailable — run a preset demo", "available_presets": ["csv_analysis"]}}))
                    return
                state["count"] += 1
                task_id = f"test-task-{state['count']}"
                state["mode"] = "approval" if payload.get("preset_id") == "demo_form" else "code"
                state["snapshots"][task_id] = 0
                body = {"task_id": task_id}
            elif path == "actions/action-1/approve":
                state["count"] += 1
                state["mode"] = "receipt"
                task_id = f"test-task-{state['count']}"
                state["snapshots"][task_id] = 0
                body = {"task_id": task_id}
            elif "/artifacts/" in path:
                route.fulfill(status=200, content_type="image/png", body=PNG)
                return
            elif path.endswith("/events"):
                events = [
                    {"id": "1", "type": "status", "data": {"status": "running"}},
                    {"id": "2", "type": "stdout", "data": {"text": "Real fixture stdout <script>window.BAD=true</script>"}},
                    {"id": "3", "type": "status", "data": {"status": "succeeded"}},
                ]
                stream = "".join(f"id: {item['id']}\ndata: {json.dumps(item)}\n\n" for item in events) + "event: end\ndata: {}\n\n"
                route.fulfill(status=200, content_type="text/event-stream", body=stream)
                return
            elif path.startswith("tasks/"):
                task_id = path.split("/")[1]
                state["snapshots"][task_id] = state["snapshots"].get(task_id, 0) + 1
                body = {"id": task_id, "pattern": "code", "source": "custom_code", "status": "succeeded" if state["snapshots"][task_id] >= 3 else "running", "summary": "CSV revenue analysis completed.", "artifacts": [], "usage": []}
                if state["mode"] == "approval":
                    url = f"/api/tasks/{task_id}/artifacts/screenshot"
                    body.update(pattern="browser", source="preset", status="awaiting_approval", summary="Form prepared. Awaiting your approval.", artifacts=[{"id": "screenshot", "name": "prepared-form.png", "mime": "image/png", "url": url}], pending_action={"id": "action-1", "title": "Demo request", "message": "Prepared message", "revision": "form-v1", "screenshot_url": url, "expires_at": "2030-01-01T00:00:00Z"})
                elif state["mode"] == "receipt":
                    body.update(pattern="browser", source="preset", status="succeeded", summary="Submission accepted. Receipt: demo-receipt-1.", result={"receipt": {"id": "demo-receipt-1", "title": "Demo request", "message": "Prepared message", "effect": "demo_record_only"}})
            else:
                route.fulfill(status=404, content_type="application/json", body='{"detail":"Not found"}')
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        page.route("**/api/**", api)
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        expect(page.get_by_role("heading", name="Real work.")).to_be_visible()
        expect(page.get_by_text("Worker connected", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Execute securely")).to_be_enabled()
        assert page.locator("body").evaluate("element => element.scrollWidth <= window.innerWidth"), "Desktop horizontal overflow"
        page.screenshot(path="/tmp/brz-dashboard-desktop.png", full_page=True)

        page.get_by_role("button", name="Execute securely").click()
        expect(page.get_by_label("Live execution logs")).to_contain_text("Real fixture stdout")
        expect(page.get_by_text("Execution stream complete", exact=True)).to_be_visible()
        assert page.evaluate("window.BAD") is None, "Sandbox output executed as HTML"

        page.get_by_role("button", name="Ask AI").click()
        page.get_by_label("What would you like to run?").fill("Analyze my CSV")
        page.get_by_role("button", name="Execute securely").click()
        expect(page.get_by_role("region", name="Execution workspace").get_by_role("alert")).to_contain_text("Live AI unavailable")
        expect(page.get_by_role("button", name="CSV analysis")).to_be_enabled()

        page.get_by_role("tab", name="Browser sandbox").click()
        page.get_by_role("button", name="Prepare a demo form").click()
        expect(page.get_by_role("heading", name="Review before anything is submitted.")).to_be_visible()
        assert not any("approve" in path for _, path in state["requests"]), "Submission occurred before approval"
        page.get_by_role("button", name="Approve this exact submission").click()
        expect(page.get_by_text("Submission accepted. Receipt: demo-receipt-1.", exact=True)).to_be_visible()
        expect(page.get_by_role("region", name="Trusted demo receipt")).to_contain_text("demo-receipt-1")
        assert sum("approve" in path for _, path in state["requests"]) == 1

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(150)
        assert page.locator("body").evaluate("element => element.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
        page.screenshot(path="/tmp/brz-dashboard-mobile.png", full_page=True)
        assert not errors, errors
        browser.close()
    print("PASS: desktop/mobile layout, custom execution, SSE logs, escaped output, visible AI fallback, explicit form approval, CSRF headers; zero browser errors")


if __name__ == "__main__":
    main()
