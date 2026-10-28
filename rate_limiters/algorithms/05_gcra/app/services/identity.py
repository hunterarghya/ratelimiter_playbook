"""Identity resolution logic for rate limiting."""


def resolve_identity(headers: dict[str, str], client_host: str | None = None) -> str:
    """Derives a consistent identity string from request headers and client host.

    Order of precedence:
    1. X-User-Id header
    2. X-API-Key header
    3. Authorization header
    4. Client host / IP
    5. anonymous fallback
    """
    if user_id := headers.get("x-user-id"):
        return f"user:{user_id}"
    if api_key := headers.get("x-api-key"):
        return f"key:{api_key}"
    if auth := headers.get("authorization"):
        return f"token:{hash(auth) & 0xFFFFFFFF:08x}"
    if client_host:
        return f"ip:{client_host}"
    return "anonymous"
