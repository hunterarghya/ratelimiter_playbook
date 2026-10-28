"""Unit tests for identity resolution strategies and spoofing defenses."""

import hashlib

from app.services.identity import (
    resolve_api_key_identity,
    resolve_composite_ip_user_identity,
    resolve_endpoint_identity,
    resolve_global_identity,
    resolve_ip_identity,
    resolve_tenant_identity,
    resolve_user_identity,
)


def test_resolve_ip_direct_client() -> None:
    headers: dict[str, str] = {}
    identity = resolve_ip_identity(headers, client_host="192.168.1.50", trusted_proxy_count=1)
    assert identity == "ip:192.168.1.50"


def test_resolve_ip_trusted_proxy_defense() -> None:
    """X-Forwarded-For spoofing defense:

    An attacker injects a fake IP '1.1.1.1' into X-Forwarded-For: '1.1.1.1, 203.0.113.1'.
    Behind 1 trusted reverse proxy (trusted_proxy_count=1), the true client IP added by our proxy
    is the rightmost one ('203.0.113.1').
    """
    headers = {"x-forwarded-for": "1.1.1.1, 203.0.113.1"}
    identity = resolve_ip_identity(headers, client_host="10.0.0.2", trusted_proxy_count=1)
    assert identity == "ip:203.0.113.1"


def test_resolve_ip_multiple_trusted_proxies() -> None:
    """When behind 2 trusted proxies (e.g. Cloudflare -> NGINX -> App):

    X-Forwarded-For: attacker_spoof, real_client, cloudflare_edge
    With trusted_proxy_count=2, the client is parts[-2] == 'real_client'.
    """
    headers = {"x-forwarded-for": "8.8.8.8, 198.51.100.25, 172.68.1.1"}
    identity = resolve_ip_identity(headers, client_host="10.0.0.2", trusted_proxy_count=2)
    assert identity == "ip:198.51.100.25"


def test_resolve_ip_fallback() -> None:
    headers: dict[str, str] = {}
    identity = resolve_ip_identity(headers, client_host=None, trusted_proxy_count=1)
    assert identity == "ip:127.0.0.1"


def test_resolve_user_identity() -> None:
    headers = {"x-user-id": "usr_9988"}
    assert resolve_user_identity(headers) == "user:usr_9988"

    assert resolve_user_identity({}) is None


def test_resolve_api_key_hashes_secret() -> None:
    raw_key = "sk_live_secret_key_12345"
    expected_digest = hashlib.sha256(raw_key.encode()).hexdigest()[:16]

    headers = {"x-api-key": raw_key}
    identity = resolve_api_key_identity(headers)
    assert identity == f"key:{expected_digest}"
    # Ensure plaintext key never appears in Redis key / identity string
    assert "sk_live" not in (identity or "")


def test_resolve_tenant_identity() -> None:
    headers = {"x-tenant-id": "org_enterprise_42"}
    assert resolve_tenant_identity(headers) == "tenant:org_enterprise_42"
    assert resolve_tenant_identity({}) is None


def test_resolve_endpoint_identity() -> None:
    headers: dict[str, str] = {}
    identity = resolve_endpoint_identity(
        headers, "POST", "/api/v1/checkout", client_host="192.168.1.1"
    )
    assert identity == "ip:192.168.1.1:POST:/api/v1/checkout"


def test_resolve_global_identity() -> None:
    assert resolve_global_identity() == "global"


def test_resolve_composite_ip_user_identity() -> None:
    # With user header
    headers = {"x-user-id": "bob"}
    identity = resolve_composite_ip_user_identity(
        headers, client_host="10.0.0.5", trusted_proxy_count=1
    )
    assert identity == "composite:ip:10.0.0.5|user:bob"

    # Without user header (anonymous fallback)
    anon_identity = resolve_composite_ip_user_identity(
        {}, client_host="10.0.0.5", trusted_proxy_count=1
    )
    assert anon_identity == "composite:ip:10.0.0.5|user:anon"
