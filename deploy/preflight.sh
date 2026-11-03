#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T worker python -c '
import json
from brz.config import Settings
from brz.sandbox import SandboxRunner
runner = SandboxRunner(Settings.from_env())
report = runner.preflight()
print(json.dumps(report, indent=2))
if not report["ready"] or not report["browser_ready"]:
    raise SystemExit(1)
result = runner.run_code("import os,json; print(json.dumps({\"uid\":os.getuid(),\"secret_absent\":\"VULTR_API_KEY\" not in os.environ,\"no_new_privs\": [line.strip() for line in open(\"/proc/self/status\") if line.startswith(\"NoNewPrivs:\")]}))", None, lambda *args: None, lambda: False)
print(json.dumps({"python_probe": result.status, "output": result.output, "details": result.details}, indent=2))
if result.status != "succeeded":
    raise SystemExit(1)
runtime = json.loads(result.output)
if runtime.get("uid") == 0 or runtime.get("secret_absent") is not True or runtime.get("no_new_privs") != ["NoNewPrivs:\t1"]:
    raise SystemExit("Runtime privilege/secret probe failed")
result = runner.run_browser({"kind":"metadata_probe", "url":"http://169.254.169.254/v1/identity/token"}, lambda *args: None, lambda: False)
print(json.dumps({"metadata_probe": result.status, "details": result.details}, indent=2))
if result.status != "blocked" or not result.details.get("policy_denials"):
    raise SystemExit(1)
'
