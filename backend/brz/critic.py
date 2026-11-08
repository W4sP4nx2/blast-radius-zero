"""Deterministic structural review for untrusted Python proposals."""
from __future__ import annotations

import ast
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# This is an early policy filter, not the containment boundary. Dynamic imports and
# runtime tricks can evade static inspection; Docker still enforces no networking.
FORBIDDEN_IMPORT_ROOTS = frozenset({
    "aiohttp",
    "ctypes",
    "ftplib",
    "http",
    "httpx",
    "imaplib",
    "paramiko",
    "poplib",
    "psycopg2",
    "pymysql",
    "requests",
    "smtplib",
    "socket",
    "ssl",
    "subprocess",
    "telnetlib",
    "urllib",
    "websockets",
})


FORBIDDEN_CALLS = frozenset({
    "__import__",
    "compile",
    "eval",
    "exec",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.fork",
    "os.forkpty",
    "os.popen",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
    "os.system",
})


def _dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class ValidationResult(BaseModel):
    """Typed handoff from deterministic validation to execution routing."""

    model_config = ConfigDict(extra="forbid", strict=True)

    is_approved: bool
    verdict: Literal["approved", "blocked", "repairable"]
    errors: list[str] = Field(default_factory=list)
    sanitized_code: str | None = None


def validate_code(code: str) -> ValidationResult:
    """Validate source without executing it in the control plane."""
    if not code.strip():
        return ValidationResult(
            is_approved=False,
            verdict="repairable",
            errors=["Python source is empty"],
        )
    if len(code.encode("utf-8")) > 64 * 1024:
        return ValidationResult(
            is_approved=False,
            verdict="blocked",
            errors=["Python source exceeds 64 KiB"],
        )
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return ValidationResult(
            is_approved=False,
            verdict="repairable",
            errors=[f"Invalid Python syntax at line {exc.lineno or 0}: {exc.msg}"],
        )

    errors: list[str] = []
    import_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            for alias in node.names:
                import_aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name.split(".", 1)[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
            root = node.module.split(".", 1)[0]
            for alias in node.names:
                import_aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
        for name in names:
            root = name.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                errors.append(f"Forbidden import detected: {name}")
        if isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                first, separator, rest = name.partition(".")
                canonical = import_aliases.get(first, first) + (separator + rest if separator else "")
                if canonical in FORBIDDEN_CALLS:
                    errors.append(f"Forbidden call detected: {canonical}")

    if errors:
        return ValidationResult(
            is_approved=False,
            verdict="blocked",
            errors=sorted(set(errors)),
        )
    return ValidationResult(
        is_approved=True,
        verdict="approved",
        sanitized_code=code,
    )
