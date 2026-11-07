"""Critic: Pydantic-validated security gate that blocks dangerous code before execution."""
import ast
from typing import Literal

from pydantic import BaseModel, Field


FORBIDDEN_IMPORTS = frozenset([
    "socket", "ssl", "urllib", "urllib.request", "urllib.error", "http", "http.client",
    "http.server", "httpx", "requests", "aiohttp", "websockets", "ftplib", "poplib", "imaplib",
    "smtplib", "telnetlib", "ldap3", "pyodbc", "pymysql", "psycopg2", "paramiko",
    "subprocess", "shlex", "os", "posix", "nt", "ctypes", "cryptography", " cryptography.hazmat",
    "pwn", "exploit", "metasploit", "pexpect", "fabric", "ansible", "salt", "fabric2",
])


class CodePlan(BaseModel):
    """Plan produced by the planner LLM. Critic validates it before execution."""
    reasoning: str = Field(
        description="Brief explanation of the approach. Max 500 characters.",
        max_length=500,
    )
    code: str = Field(
        description="The Python 3.13 standard-library code to execute. Must not exceed 64 KiB.",
        max_length=64 * 1024,
    )
    requires_network: bool = Field(
        description="True if the code attempts external network access.",
        default=False,
    )

    def model_post_init(self, __context):
        # Validate code safety after initialization
        self._validate_code()

    def _validate_code(self) -> None:
        # Size check (redundant with Field but explicit)
        if len(self.code.encode("utf-8")) > 64 * 1024:
            raise ValueError("Code exceeds 64 KiB limit")

        # AST parsing
        try:
            tree = ast.parse(self.code)
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax: {e}")

        # Import check
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in FORBIDDEN_IMPORTS:
                        raise ValueError(f"Forbidden import: {name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in FORBIDDEN_IMPORTS:
                        raise ValueError(f"Forbidden import from: {top}")


class ValidationResult(BaseModel):
    """Critic outcome: approved or blocked with specific errors."""
    is_approved: bool
    verdict: Literal["approved", "blocked", "repairable"] = "blocked"
    errors: list[str] = Field(default_factory=list)
    sanitized_code: str | None = None


def validate_plan(plan: CodePlan) -> ValidationResult:
    """Run the Critic on a CodePlan. Returns ValidationResult without raising."""
    errors = []
    try:
        validated = CodePlan.model_validate_json(plan.model_dump_json())
        if validated.requires_network:
            errors.append("Policy violation: External network access is prohibited.")
            return ValidationResult(is_approved=False, verdict="blocked", errors=errors)
        return ValidationResult(
            is_approved=True, verdict="approved", errors=[], sanitized_code=validated.code
        )
    except Exception as e:
        msg = str(e)
        if "SyntaxError" in msg or "IndentationError" in msg or "NameError" in msg:
            return ValidationResult(
                is_approved=False, verdict="repairable", errors=[msg], sanitized_code=None
            )
        return ValidationResult(is_approved=False, verdict="blocked", errors=[msg])
