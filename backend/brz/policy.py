import ipaddress
from urllib.parse import urlsplit


def research_url(value: str, domains: list[str]) -> str:
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").encode("idna").decode().lower()
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid research URL") from exc
    if parts.scheme != "https" or port not in (None, 443) or parts.username is not None or parts.password is not None or not host:
        raise ValueError("Research requires an approved HTTPS destination on port 443")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Research IP literals are not allowed")
    if host not in domains:
        raise ValueError("Research domain is not on the administrator allowlist")
    return value
