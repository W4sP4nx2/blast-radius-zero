"""Real containment checks. Never silently replace Docker with a subprocess."""
import json
import os
import time
import pytest
from brz.config import Settings
from brz.presets import CSV_CODE
from brz.sandbox import SandboxRunner

pytestmark = pytest.mark.integration


@pytest.fixture
def runner():
    if os.getenv("BRZ_INTEGRATION") != "1":
        pytest.skip("Set BRZ_INTEGRATION=1 on an isolated Linux Docker host with built images")
    result = SandboxRunner(Settings.from_env())
    assert result.preflight()["ready"], "Docker resource-control preflight failed"
    yield result
    result.reap()


def run(runner, code):
    return runner.run_code(code, None, lambda *_: None, lambda: False)


def test_success_csv_artifacts_and_precompletion_logs(runner):
    observed = []
    before = time.monotonic()
    result = runner.run_code(CSV_CODE, None, lambda kind, data: observed.append((kind, time.monotonic() - before, data)), lambda: False)
    elapsed = time.monotonic() - before
    assert result.status == "succeeded", result.error
    assert json.loads(result.artifacts["analysis.json"])["total_revenue"] == 130
    assert "summary.csv" in result.artifacts
    assert any(kind == "stdout" and when < elapsed - 0.2 for kind, when, _ in observed)


def test_uploaded_csv_is_staged_inside_tmpfs(runner):
    result = runner.run_code(CSV_CODE, b'category,quantity,unit_price\nCompute,2,3\n', lambda *_: None, lambda: False)
    assert result.status == 'succeeded', result.error
    summary = json.loads(result.artifacts['analysis.json'])
    assert summary['rows'] == 1 and summary['total_revenue'] == 6


@pytest.mark.parametrize("payload", [
    "import urllib.request; urllib.request.urlopen('https://vultr.com',timeout=2)",
    "import socket; socket.create_connection(('1.1.1.1',443),timeout=2)",
])
def test_network_denial_dns_and_direct_ip(runner, payload):
    result = run(runner, payload)
    assert result.status == "failed" and result.details["exit_code"] != 0


def test_timeout_and_removal(runner):
    result = run(runner, "while True: pass")
    assert result.status == "timed_out"
    assert 9 <= result.details["duration_ms"] / 1000 <= 16
    assert not runner._docker().containers.list(all=True, filters={"label": "brz.role=code"})


def test_memory_failure_does_not_assume_137_is_oom(runner):
    result = run(runner, "b=bytearray(600*1024*1024)")
    assert result.status in ("oom_killed", "failed")
    if result.status == "oom_killed":
        assert result.details["oom_killed"] is True


def test_host_secret_absence_and_runtime_privilege(runner, monkeypatch):
    monkeypatch.setenv("BRZ_TEST_SECRET", "must-not-enter-sandbox")
    result = run(runner, "import os,json; print(json.dumps({'secret':os.getenv('BRZ_TEST_SECRET'),'key':os.getenv('VULTR_API_KEY'),'uid':os.getuid(),'privs':[x.strip() for x in open('/proc/self/status') if x.startswith('NoNewPrivs:')]}))")
    data = json.loads(result.output)
    assert data["secret"] is None and data["key"] is None and data["uid"] != 0
    assert data["privs"] == ["NoNewPrivs:\t1"]


def test_read_only_and_tmp_reset(runner):
    readonly = run(runner, "open('/home/sandbox/test.txt','w').write('bad')")
    assert readonly.status == "failed"
    assert "Read-only file system" in readonly.output
    assert run(runner, "open('/tmp/transient','w').write('ok')").status == "succeeded"
    clean = run(runner, "import os; print(os.path.exists('/tmp/transient'))")
    assert clean.status == "succeeded" and clean.output.strip() == "False"


def test_output_flood_is_bounded_and_cleaned(runner):
    result = run(runner, "while True: print('x'*4096,flush=True)")
    assert result.status == "output_limit"
    assert len(result.output.encode()) <= 1024 * 1024


def test_pid_limit_without_exhausting_host(runner):
    payload = '''import os,signal,time
pids=[]
try:
    for _ in range(80):
        pid=os.fork()
        if pid==0:
            time.sleep(20)
            os._exit(0)
        pids.append(pid)
except OSError:
    print('PID_LIMIT',len(pids),flush=True)
finally:
    for pid in pids:
        try: os.kill(pid,signal.SIGKILL)
        except ProcessLookupError: pass
    for pid in pids:
        try: os.waitpid(pid,0)
        except ChildProcessError: pass
'''
    result = run(runner, payload)
    assert result.status == 'succeeded' and 'PID_LIMIT' in result.output


def test_tmpfs_size_is_bounded(runner):
    result = run(runner, "open('/tmp/large','wb').write(b'x'*(70*1024*1024))")
    assert result.status == 'failed' and 'No space left on device' in result.output


def test_cancellation_removes_running_container(runner):
    cancelled = __import__('threading').Event()
    result = runner.run_code("print('started',flush=True)\nwhile True: pass", None,
                            lambda *_: cancelled.set(), cancelled.is_set)
    assert result.status == 'cancelled'
    assert not runner._docker().containers.list(all=True, filters={'label': 'brz.role=code'})


@pytest.mark.browser_integration
def test_browser_metadata_denial_and_real_capture(runner):
    if os.getenv("BRZ_BROWSER_INTEGRATION") != "1":
        pytest.skip("Set BRZ_BROWSER_INTEGRATION=1 after target-host firewall/DNS/TLS setup")
    assert runner.preflight()["browser_ready"]
    denied = runner.run_browser({"kind": "metadata_probe", "url": "http://169.254.169.254/v1/identity/token"}, lambda *_: None, lambda: False)
    assert denied.status == "blocked" and denied.details["policy_denials"]
    capture = runner.run_browser({"kind": "research", "url": "https://news.ycombinator.com/"}, lambda *_: None, lambda: False)
    assert capture.status == "succeeded", capture.error
    assert len(capture.details["evidence"]) == 3 and capture.artifacts["screenshot.png"].startswith(b"\x89PNG")
