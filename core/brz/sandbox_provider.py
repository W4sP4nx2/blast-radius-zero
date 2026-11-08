"""Execution-provider contract used by the trusted coordinator."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .sandbox import RunResult

EventEmitter = Callable[[str, dict], None]
CancellationCheck = Callable[[], bool]


def _discard_event(_kind: str, _data: dict) -> None:
    pass


def _never_cancelled() -> bool:
    return False


class BaseSandboxProvider(ABC):
    """Contract for code and fixed browser execution environments."""

    name: str

    @abstractmethod
    def initialize(self) -> dict:
        """Check prerequisites and return code/browser readiness."""

    @abstractmethod
    def exec_code(
        self,
        script: str,
        upload: bytes | None = None,
        emit: EventEmitter = _discard_event,
        cancelled: CancellationCheck = _never_cancelled,
    ) -> "RunResult":
        """Execute Python under provider-owned fixed policy."""

    @abstractmethod
    def exec_browser(
        self,
        payload: dict,
        emit: EventEmitter = _discard_event,
        cancelled: CancellationCheck = _never_cancelled,
    ) -> "RunResult":
        """Execute one fixed browser operation under provider-owned policy."""

    @abstractmethod
    def teardown(self) -> None:
        """Remove resources owned by this coordinator."""
