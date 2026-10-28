"""Integration tests verifying HTTP endpoints, headers, and mode switching."""

from unittest.mock import patch

import pytest
from app.main import app, repository, service
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_shadow_endpoint_returns_200_even_when_exhausted() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simulate Redis returning denial (quota exceeded)
        with patch.object(repository, "evaluate", return_value=(0, 0, 4, 4, 5)):
            resp = await client.get("/demo/shadow", headers={"X-User-Id": "alice"})
            # Must return 200 OK
            assert resp.status_code == 200
            assert resp.headers.get("X-RateLimit-Mode") == "shadow"
            assert resp.headers.get("X-RateLimit-Action") == "shadow_denied"
            assert resp.headers.get("X-RateLimit-Would-Block") == "true"
            assert resp.headers.get("X-RateLimit-Retry-After") == "4"


@pytest.mark.asyncio
async def test_enforce_endpoint_returns_429_when_exhausted() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "evaluate", return_value=(0, 0, 4, 4, 5)):
            resp = await client.get("/demo/enforce", headers={"X-User-Id": "alice"})
            assert resp.status_code == 429
            assert resp.headers.get("X-RateLimit-Mode") == "enforce"
            assert resp.headers.get("X-RateLimit-Action") == "denied"
            assert resp.headers.get("Retry-After") == "4"
            data = resp.json()
            assert data["detail"]["error"] == "rate_limited"


@pytest.mark.asyncio
async def test_allowlist_endpoint_bypasses_rate_limit() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "evaluate") as mock_eval:
            resp = await client.get("/demo/allowlist", headers={"X-User-Id": "admin"})
            assert resp.status_code == 200
            assert resp.headers.get("X-RateLimit-Mode") == "allowlist"
            assert resp.headers.get("X-RateLimit-Action") == "bypassed"
            mock_eval.assert_not_called()


@pytest.mark.asyncio
async def test_admin_mode_toggle_flips_dynamic_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "evaluate", return_value=(0, 0, 5, 5, 5)):
            # 1. Initially set to shadow
            service.set_mode("shadow")
            resp_shadow = await client.get("/demo/dynamic", headers={"X-User-Id": "alice"})
            assert resp_shadow.status_code == 200
            assert resp_shadow.headers.get("X-RateLimit-Action") == "shadow_denied"

            # 2. Call admin endpoint to flip mode to enforce
            resp_admin = await client.post("/admin/mode?mode=enforce")
            assert resp_admin.status_code == 200
            assert resp_admin.json() == {"status": "ok", "mode": "enforce"}

            # 3. Request now returns 429 with ZERO code change
            resp_enforce = await client.get("/demo/dynamic", headers={"X-User-Id": "alice"})
            assert resp_enforce.status_code == 429
            assert resp_enforce.headers.get("X-RateLimit-Action") == "denied"
