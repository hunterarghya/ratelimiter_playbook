"""Integration tests for failure modes endpoints under simulated Redis failure."""

from unittest.mock import patch

import pytest
from app.main import app, repository
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_fail_open_route_serves_during_redis_outage() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "evaluate", side_effect=ConnectionError("Redis down")):
            resp = await client.get("/demo/fail-open", headers={"X-User-Id": "alice"})
            assert resp.status_code == 200
            assert resp.headers.get("X-RateLimit-Source") == "fail_open"
            assert "RateLimit-Limit" in resp.headers


@pytest.mark.asyncio
async def test_fail_closed_route_returns_503_during_redis_outage() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "evaluate", side_effect=ConnectionError("Redis down")):
            resp = await client.get("/demo/fail-closed", headers={"X-User-Id": "alice"})
            assert resp.status_code == 503
            assert resp.headers.get("X-RateLimit-Source") == "fail_closed"
            data = resp.json()
            assert data["detail"]["error"] == "service_unavailable"


@pytest.mark.asyncio
async def test_fallback_route_enforces_limit_during_redis_outage() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "evaluate", side_effect=ConnectionError("Redis down")):
            # Exhaust the local fallback
            got_429 = False
            for _ in range(15):
                resp = await client.get("/demo/fallback", headers={"X-User-Id": "alice"})
                if resp.status_code == 429:
                    got_429 = True
                    assert resp.headers.get("X-RateLimit-Source") == "local_fallback"
                    assert resp.headers.get("RateLimit-Remaining") == "0"
                    break
            assert got_429 is True


@pytest.mark.asyncio
async def test_health_reports_degraded_when_redis_down() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(repository, "ping", return_value=False):
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "degraded", "redis": "down"}
