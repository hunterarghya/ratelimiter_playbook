"""Invariant tests against real Redis for GCRA Lua script."""

import os
import time
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis
from app.repositories.redis_repository import RedisRepository


@pytest.fixture
async def redis_client() -> AsyncIterator[redis.Redis]:
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client = redis.from_url(url)
    yield client
    await client.aclose()


@pytest.fixture
async def repository(redis_client: redis.Redis) -> RedisRepository:
    return RedisRepository(redis_client)


@pytest.mark.asyncio
async def test_denied_requests_do_not_advance_tat(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_deny_{int(time.time() * 1000)}"
    rule_name = "test_deny"
    t_ms = 500.0
    tau_ms = 1500.0  # burst 3
    burst = 3
    key = f"rl:{{{identity}}}:{rule_name}:gcra"

    # Drain burst (3 requests)
    for _ in range(3):
        allowed, _, _, _, _ = await repository.evaluate_gcra(
            identity, rule_name, t_ms=t_ms, tau_ms=tau_ms, burst=burst
        )
        assert allowed == 1

    # Read TAT in Redis
    raw_tat_before = await redis_client.get(key)
    assert raw_tat_before is not None

    # Send 5 denied requests
    for _ in range(5):
        allowed, _, _, _, _ = await repository.evaluate_gcra(
            identity, rule_name, t_ms=t_ms, tau_ms=tau_ms, burst=burst
        )
        assert allowed == 0

    # Verify TAT did not advance
    raw_tat_after = await redis_client.get(key)
    assert raw_tat_after == raw_tat_before


@pytest.mark.asyncio
async def test_idle_key_has_ttl(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_ttl_{int(time.time() * 1000)}"
    rule_name = "test_ttl"
    key = f"rl:{{{identity}}}:{rule_name}:gcra"

    await repository.evaluate_gcra(
        identity, rule_name, t_ms=500.0, tau_ms=2000.0, burst=4
    )
    ttl = await redis_client.ttl(key)
    assert ttl > 0, f"Expected key to have positive TTL, got {ttl}"


@pytest.mark.asyncio
async def test_exact_worked_example_invariants(
    repository: RedisRepository,
) -> None:
    """Verifies the exact table from 02-algorithms.md worked example.

    Config: 2 req/s, burst 4 -> T = 500ms, tau = 2000ms.
    """
    identity = f"inv_example_{int(time.time() * 1000)}"
    rule_name = "test_example"
    t_ms = 500.0
    tau_ms = 2000.0
    burst = 4
    base_time_ms = 1_700_000_000_000

    # Requests 1 to 4 at t=0
    for expected_remaining in [3, 2, 1, 0]:
        allowed, remaining, retry_after, _, _ = await repository.evaluate_gcra(
            identity, rule_name, t_ms, tau_ms, burst, cost=1, now_ms=base_time_ms
        )
        assert allowed == 1
        assert remaining == expected_remaining
        assert retry_after == 0

    # Request 5 at t=0 -> DENIED
    allowed, remaining, retry_after, _, _ = await repository.evaluate_gcra(
        identity, rule_name, t_ms, tau_ms, burst, cost=1, now_ms=base_time_ms
    )
    assert allowed == 0
    assert remaining == 0
    assert retry_after >= 1

    # Request 6 at t=500ms -> ALLOWED
    allowed, remaining, retry_after, _, _ = await repository.evaluate_gcra(
        identity, rule_name, t_ms, tau_ms, burst, cost=1, now_ms=base_time_ms + 500
    )
    assert allowed == 1
    assert remaining == 0
    assert retry_after == 0
