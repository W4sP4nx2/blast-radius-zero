"""Administrator-controlled sandbox provider selection."""
from __future__ import annotations

from .adapters.docker_adapter import DockerSandboxProvider
from .adapters.native_adapter import NativeSandboxProvider
from .sandbox_provider import BaseSandboxProvider


def get_sandbox_provider(settings) -> BaseSandboxProvider:
    mode = settings.sandbox_runtime
    if mode == "docker":
        return DockerSandboxProvider(settings)
    if mode == "native":
        return NativeSandboxProvider(settings)
    # Settings.from_env validates this too. Keep factory fail-closed for direct
    # Settings construction and future callers.
    raise ValueError(f"Unsupported SANDBOX_RUNTIME: {mode}")
