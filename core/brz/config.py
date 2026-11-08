"""Administrator-only configuration. Never populated from task/model input."""
from dataclasses import dataclass, field
import os
from urllib.parse import urlsplit


def env_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    redis_url: str = "redis://localhost:6379/0"
    app_origin: str = "http://localhost:3000"
    sandbox_runtime: str = "docker"
    audit_db_path: str = "/tmp/brz-audit/audit.db"
    native_home: str = "/var/lib/brz/native"
    native_mcp_binary: str = "/usr/local/lib/brz/mcp-stdio"
    ai_enabled: bool = False
    vultr_api_key: str = field(default="", repr=False)
    vultr_text_model: str = ""
    vultr_vision_model: str = ""
    inference_url: str = "https://api.vultrinference.com/v1"
    python_image: str = "brz-python-sandbox:local"
    browser_image: str = "brz-browser-sandbox:local"
    proxy_image: str = "brz-egress-proxy:local"
    browser_domains: list[str] = field(default_factory=lambda: ["news.ycombinator.com"])
    demo_url: str = "https://demo.example.com:8443"
    demo_ip: str = ""
    egress_dns: str = "1.1.1.1"
    docker_timeout: int = 5
    task_ttl: int = 900
    session_ttl: int = 3600
    approval_ttl: int = 300
    starts_per_minute: int = 6
    ai_tasks_per_hour: int = 3
    provider_per_minute: int = 20
    queue_limit: int = 8
    redis_high_water_bytes: int = 160 * 1024 * 1024

    @classmethod
    def from_env(cls):
        origin = os.getenv("APP_ORIGIN", "").rstrip("/")
        if not origin:
            domain = os.getenv("APP_DOMAIN", "")
            origin = f"https://{domain}" if domain else "http://localhost:3000"
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path:
            raise ValueError("APP_ORIGIN must be an HTTP(S) origin")
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ValueError("Public deployments require an HTTPS APP_ORIGIN")
        sandbox_runtime = os.getenv("SANDBOX_RUNTIME", "docker").lower()
        if sandbox_runtime not in {"docker", "native"}:
            raise ValueError("SANDBOX_RUNTIME must be docker or native")
        return cls(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            app_origin=origin,
            sandbox_runtime=sandbox_runtime,
            audit_db_path=os.getenv("AUDIT_DB_PATH", "/tmp/brz-audit/audit.db"),
            native_home=os.getenv("NATIVE_HOME", "/var/lib/brz/native"),
            native_mcp_binary=os.getenv("NATIVE_MCP_BINARY", "/usr/local/lib/brz/mcp-stdio"),
            ai_enabled=os.getenv("AI_ENABLED", "false").lower() == "true",
            vultr_api_key=os.getenv("VULTR_API_KEY", ""),
            vultr_text_model=os.getenv("VULTR_TEXT_MODEL", os.getenv("VULTR_PLANNER_MODEL", "")),
            vultr_vision_model=os.getenv("VULTR_VISION_MODEL", ""),
            python_image=os.getenv("PYTHON_IMAGE", "brz-python-sandbox:local"),
            browser_image=os.getenv("BROWSER_IMAGE", "brz-browser-sandbox:local"),
            proxy_image=os.getenv("PROXY_IMAGE", "brz-egress-proxy:local"),
            browser_domains=[x.strip().lower() for x in os.getenv("BROWSER_DOMAINS", "news.ycombinator.com").split(",") if x.strip()],
            demo_url=os.getenv("DEMO_URL", f"https://{os.getenv('DEMO_DOMAIN', 'demo.example.com')}:8443"),
            demo_ip=os.getenv("DEMO_IP", ""),
            egress_dns=os.getenv("EGRESS_DNS", "1.1.1.1"),
            starts_per_minute=env_int("TASK_STARTS_PER_MINUTE", 6),
            ai_tasks_per_hour=env_int("AI_TASKS_PER_HOUR", 3),
            provider_per_minute=env_int("PROVIDER_REQUESTS_PER_MINUTE", 20),
        )

    @property
    def secure_cookies(self):
        return self.app_origin.startswith("https://")


CODE_POLICY = {"network": "none", "memory_mib": 256, "cpu": 0.5,
               "pids": 64, "timeout_seconds": 10, "read_only": True, "tmp_mib": 64}
BROWSER_POLICY = {"network": "isolated + filtered proxy", "memory_mib": 512,
                  "cpu": 1, "pids": 256, "timeout_seconds": 30, "read_only": True}
TERMINAL = {"succeeded", "failed", "blocked", "timed_out", "oom_killed",
            "cancelled", "infrastructure_error", "output_limit", "awaiting_approval"}
