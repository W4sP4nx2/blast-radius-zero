"""Adapter for the verified Docker-on-Vultr sandbox implementation."""
from __future__ import annotations

from ..sandbox import SandboxRunner
from ..sandbox_provider import BaseSandboxProvider


class DockerSandboxProvider(BaseSandboxProvider):
    """Preserve the existing Docker lifecycle behind the provider contract."""

    name = "docker"

    def __init__(self, settings, runner: SandboxRunner | None = None):
        self.runner = runner or SandboxRunner(settings)

    def initialize(self) -> dict:
        report = self.runner.preflight()
        return {**report, "provider": self.name}

    def exec_code(self, script, upload=None, emit=lambda *_: None, cancelled=lambda: False):
        return self.runner.run_code(script, upload, emit, cancelled)

    def exec_browser(self, payload, emit=lambda *_: None, cancelled=lambda: False):
        return self.runner.run_browser(payload, emit, cancelled)

    def teardown(self) -> None:
        self.runner.reap()
