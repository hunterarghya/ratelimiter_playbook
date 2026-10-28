"""Invariant tests against real Redis for concurrency lease Lua script and ZREM release."""

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
async def test_denied_requests_do_not_add_to_zset(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_deny_{int(time.time() * 1000)}"
    rule_name = "test_deny"
    limit = 2
    key = f"rl:{{{identity}}}:{rule_name}:leases"

    # Fill slots (2 leases)
    a1, _, _, _, _ = await repository.acquire_lease(identity, rule_name, limit, "lease-1", 30_000)
    a2, _, _, _, _ = await repository.acquire_lease(identity, rule_name, limit, "lease-2", 30_000)
    assert a1 == 1 and a2 == 1

    count_before = await redis_client.zcard(key)
    assert count_before == 2

    # Send 5 denied requests
    for i in range(5):
        allowed, _, _, _, _ = await repository.acquire_lease(
            identity, rule_name, limit, f"lease-overflow-{i}", 30_000
        )
        assert allowed == 0

    count_after = await redis_client.zcard(key)
    assert count_after == 2


@pytest.mark.asyncio
async def test_idle_key_has_ttl(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_ttl_{int(time.time() * 1000)}"
    rule_name = "test_ttl"
    key = f"rl:{{{identity}}}:{rule_name}:leases"

    await repository.acquire_lease(identity, rule_name, 2, "lease-ttl", 30_000)
    ttl = await redis_client.ttl(key)
    assert ttl > 0, f"Expected key to have positive TTL, got {ttl}"


@pytest.mark.asyncio
async def test_crash_recovery_expired_lease_cleaned_on_acquire(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    """Verifies that when a worker crashes, the next acquire cleans expired leases automatically."""
    identity = f"inv_crash_{int(time.time() * 1000)}"
    rule_name = "test_crash"
    limit = 1
    base_time_ms = 1_700_000_000_000
    lease_ttl_ms = 10_000
    key = f"rl:{{{identity}}}:{rule_name}:leases"

    # Worker A acquires lease at t=0
    a1, _, _, _, _ = await repository.acquire_lease(
        identity, rule_name, limit, "job-A", lease_ttl_ms, now_ms=base_time_ms
    )
    assert a1 == 1

    # Worker B tries at t=5s (lease still valid) -> full
    a2, _, _, _, _ = await repository.acquire_lease(
        identity, rule_name, limit, "job-B", lease_ttl_ms, now_ms=base_time_ms + 5_000
    )
    assert a2 == 0

    # Worker A crashed without calling release!
    # At t=11s, Worker C arrives -> job-A is expired (score 10s <= 11s) -> cleaned -> job-C allowed
    a3, remaining, _, _, _ = await repository.acquire_lease(
        identity, rule_name, limit, "job-C", lease_ttl_ms, now_ms=base_time_ms + 11_000
    )
    assert a3 == 1
    assert remaining == 0

    # Verify job-A was removed and job-C is present in ZSET
    members = await redis_client.zrange(key, 0, -1)
    member_strs = [m.decode() if isinstance(m, bytes) else str(m) for m in members]
    assert "job-A" not in member_strs
    assert "job-C" in member_strs


@pytest.mark.asyncio
async def test_client_release_removes_lease(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_rel_{int(time.time() * 1000)}"
    rule_name = "test_release"
    key = f"rl:{{{identity}}}:{rule_name}:leases"

    await repository.acquire_lease(identity, rule_name, 2, "lease-to-free", 30_000)
    assert await redis_client.zcard(key) == 1

    # Client executes ZREM
    released = await repository.release_lease(identity, rule_name, "lease-to-free")
    assert released is True
    assert await redis_client.zcard(key) == 0
