"""Identity resolution logic for rate limiting."""


def resolve_identity(headers: dict[str, str], client_host: str | None = None) -> str:
    """Derives a consistent identity string from request headers and client host.

    Order of precedence:
    1. X-User-Id header -> user:<id>
    2. X-API-Key header -> api_key:<key>
    3. Client IP (from X-Forwarded-For or client_host) -> ip:<ip>
    """
    user_id = headers.get("x-user-id")
    if user_id:
        return f"user:{user_id.strip()}"

    api_key = headers.get("x-api-key")
    if api_key:
        return f"api_key:{api_key.strip()}"

    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        return f"ip:{ip}"

    ip = client_host or "127.0.0.1"
    return f"ip:{ip}"
