"""Pluggable identity resolution strategies for rate limiting."""

import hashlib


def resolve_client_ip(
    headers: dict[str, str],
    client_host: str | None = None,
    trusted_proxy_count: int = 1,
) -> str:
    """Safely extracts client IP preventing X-Forwarded-For spoofing.

    When behind N trusted reverse proxies, the genuine client IP is the N-th
    IP from the RIGHT of the X-Forwarded-For list. The leftmost IP must never
    be trusted blindly because an attacker can forge it in their request.
    """
    xff = headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            if len(parts) >= trusted_proxy_count and trusted_proxy_count > 0:
                return parts[-trusted_proxy_count]
            return parts[-1]
    return client_host or "127.0.0.1"


def resolve_ip_identity(
    headers: dict[str, str],
    client_host: str | None = None,
    trusted_proxy_count: int = 1,
) -> str:
    """Resolves IP identity: rl:{ip:X}:..."""
    ip = resolve_client_ip(headers, client_host, trusted_proxy_count)
    return f"ip:{ip}"


def resolve_user_identity(headers: dict[str, str]) -> str | None:
    """Resolves authenticated user ID: rl:{user:X}:..."""
    if user_id := headers.get("x-user-id"):
        return f"user:{user_id}"
    return None


def resolve_api_key_identity(headers: dict[str, str]) -> str | None:
    """Resolves API key hashed with SHA-256 to avoid storing raw secrets in Redis."""
    if api_key := headers.get("x-api-key"):
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        return f"key:{digest}"
    return None


def resolve_tenant_identity(headers: dict[str, str]) -> str | None:
    """Resolves tenant / organization ID for B2B SaaS fairness: rl:{tenant:X}:..."""
    if tenant_id := headers.get("x-tenant-id"):
        return f"tenant:{tenant_id}"
    return None


def resolve_endpoint_identity(
    headers: dict[str, str],
    method: str,
    path: str,
    client_host: str | None = None,
    trusted_proxy_count: int = 1,
) -> str:
    """Resolves endpoint identity combining caller with route: rl:{caller:method:path}:..."""
    caller = resolve_user_identity(headers) or resolve_ip_identity(
        headers, client_host, trusted_proxy_count
    )
    return f"{caller}:{method}:{path}"


def resolve_global_identity() -> str:
    """Resolves global system-wide identity: rl:{global}:... (hot key warning)."""
    return "global"


def resolve_composite_ip_user_identity(
    headers: dict[str, str],
    client_host: str | None = None,
    trusted_proxy_count: int = 1,
) -> str:
    """Resolves composite dual-key: rl:{ip:X|user:Y}:..."""
    ip = resolve_client_ip(headers, client_host, trusted_proxy_count)
    user = headers.get("x-user-id", "anon")
    return f"composite:ip:{ip}|user:{user}"
