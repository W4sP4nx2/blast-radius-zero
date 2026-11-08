from types import SimpleNamespace

import pytest

from brz.adapters.docker_adapter import DockerSandboxProvider
from brz.adapters.native_adapter import NativeSandboxProvider
from brz.config import Settings
from brz.sandbox import RunResult
from brz.sandbox_factory import get_sandbox_provider


class RunnerDouble:
    def __init__(self):
        self.calls = []

    def preflight(self):
        self.calls.append("initialize")
        return {"ready": True, "browser_ready": True}

    def run_code(self, script, upload, emit, cancelled):
        self.calls.append(("code", script, upload))
        return RunResult("succeeded", output="ok")

    def run_browser(self, payload, emit, cancelled):
        self.calls.append(("browser", payload))
        return RunResult("succeeded")

    def reap(self):
        self.calls.append("teardown")


def test_docker_adapter_preserves_verified_runner_contract():
    runner = RunnerDouble()
    provider = DockerSandboxProvider(Settings(), runner=runner)
    assert provider.initialize()["ready"] is True
    assert provider.exec_code("print(1)", b"csv").status == "succeeded"
    assert provider.exec_browser({"kind": "research"}).status == "succeeded"
    provider.teardown()
    assert runner.calls == [
        "initialize",
        ("code", "print(1)", b"csv"),
        ("browser", {"kind": "research"}),
        "teardown",
    ]


def test_native_adapter_fails_closed_without_executing(tmp_path):
    settings = Settings(
        sandbox_runtime="native",
        native_home=str(tmp_path),
        native_mcp_binary=str(tmp_path / "mcp-stdio"),
    )
    provider = NativeSandboxProvider(settings)
    assert provider.initialize()["ready"] is False
    code = provider.exec_code("print('must not run')")
    browser = provider.exec_browser({"kind": "research"})
    assert code.status == browser.status == "infrastructure_error"
    assert code.details == {"provider": "native", "executed": False}
    assert browser.details == {"provider": "native", "executed": False}


def test_factory_defaults_to_docker_and_rejects_unknown_mode():
    assert isinstance(get_sandbox_provider(Settings()), DockerSandboxProvider)
    assert isinstance(
        get_sandbox_provider(Settings(sandbox_runtime="native")),
        NativeSandboxProvider,
    )
    with pytest.raises(ValueError, match="Unsupported SANDBOX_RUNTIME"):
        get_sandbox_provider(Settings(sandbox_runtime="process"))


def test_settings_reject_unknown_runtime(monkeypatch):
    monkeypatch.setenv("SANDBOX_RUNTIME", "process")
    with pytest.raises(ValueError, match="docker or native"):
        Settings.from_env()
