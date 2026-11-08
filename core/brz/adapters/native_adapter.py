"""Fail-closed placeholder for a future Native execution provider."""
from __future__ import annotations

from pathlib import Path

from ..sandbox import RunResult
from ..sandbox_provider import BaseSandboxProvider


class NativeSandboxProvider(BaseSandboxProvider):
    """Represent the requested provider without pretending MCP is a sandbox.

    The public withnative/native project currently exposes a SQLite-backed MCP
    context engine. It does not expose ephemeral Python/browser execution or the
    resource/network controls required by Blast Radius Zero. Selecting this
    provider therefore makes execution unavailable rather than falling back.
    """

    name = "native"

    def __init__(self, settings):
        self.binary = Path(settings.native_mcp_binary)
        self.home = Path(settings.native_home)

    def initialize(self) -> dict:
        installed = self.binary.is_file()
        reason = (
            "Native MCP is installed, but its public interface is not an isolated "
            "code or browser runtime"
            if installed
            else "Native MCP binary is not installed; no Native execution runtime is available"
        )
        return {
            "ready": False,
            "browser_ready": False,
            "reason": reason,
            "browser_reason": reason,
            "provider": self.name,
            "context_engine_installed": installed,
        }

    def exec_code(self, script, upload=None, emit=lambda *_: None, cancelled=lambda: False):
        return RunResult(
            "infrastructure_error",
            error="Native execution is unavailable: public withnative/native is an MCP context engine, not a sandbox runtime",
            details={"provider": self.name, "executed": False},
        )

    def exec_browser(self, payload, emit=lambda *_: None, cancelled=lambda: False):
        return RunResult(
            "infrastructure_error",
            error="Native browser execution is unavailable: no isolated Playwright interface is published",
            details={"provider": self.name, "executed": False},
        )

    def teardown(self) -> None:
        # No execution resource can be created by this fail-closed adapter.
        return None
