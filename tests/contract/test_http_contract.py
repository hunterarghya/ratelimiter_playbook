"""Contract tests ensuring every rate limiter sub-project adheres to the uniform HTTP contract."""

import time

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_endpoint_contract(target_url: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{target_url}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("redis") == "up"


@pytest.mark.asyncio
async def test_metrics_endpoint_contract(target_url: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{target_url}/metrics")
        assert resp.status_code == 200
        content = resp.text
        assert "rl_decisions_total" in content


@pytest.mark.asyncio
async def test_demo_endpoint_and_429_denial_contract(target_url: str) -> None:
    headers = {"X-User-Id": f"contract_{int(time.time()*1000)}"}
    async with httpx.AsyncClient() as client:
        # Step 1: Send requests until we observe a 429
        got_429 = False
        denied_response = None
        for _ in range(15):
            resp = await client.get(f"{target_url}/demo/limited", headers=headers)
            if resp.status_code == 200:
                assert "RateLimit-Limit" in resp.headers
                assert "RateLimit-Remaining" in resp.headers
                assert "RateLimit-Reset" in resp.headers
            elif resp.status_code == 429:
                got_429 = True
                denied_response = resp
                break

        assert got_429 is True, "Expected to trigger 429 after rapid requests"
        assert denied_response is not None

        # Verify 429 contract headers
        assert "Retry-After" in denied_response.headers
        assert "RateLimit-Limit" in denied_response.headers
        assert "RateLimit-Remaining" in denied_response.headers
        assert denied_response.headers["RateLimit-Remaining"] == "0"
        assert "RateLimit-Reset" in denied_response.headers

        # Verify 429 contract JSON body
        body = denied_response.json()
        detail = body.get("detail", body)
        assert detail.get("error") == "rate_limited"
        assert "rule" in detail
        assert "retry_after_seconds" in detail


@pytest.mark.asyncio
async def test_debug_state_endpoint_contract(target_url: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{target_url}/debug/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data
        assert "pattern" in data
