"""Concurrency test: 200 parallel requests against limit N using acquire_lease Lua script."""

import asyncio
import os
import time
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis
from app.repositories.redis_repository import RedisRepository


@pytest.fixture
async def redis_client() -> AsyncIterator[redis.Redis]:
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client = redis.from_url(url, max_connections=300)
    yield client
    await client.aclose()


@pytest.fixture
async def repository(redis_client: redis.Redis) -> RedisRepository:
    return RedisRepository(redis_client)


@pytest.mark.asyncio
async def test_200_parallel_requests_allows_exact_limit(
    repository: RedisRepository,
) -> None:
    identity = f"race_{int(time.time() * 1000)}"
    rule_name = "burst_test"
    limit = 10
    lease_ttl_ms = 60_000

    async def single_call(idx: int) -> int:
        lease_id = f"worker-{idx}"
        allowed, _, _, _, _ = await repository.acquire_lease(
            identity=identity,
            rule_name=rule_name,
            limit=limit,
            lease_id=lease_id,
            lease_ttl_ms=lease_ttl_ms,
        )
        return allowed

    # Fire 200 coroutines concurrently
    results = await asyncio.gather(*(single_call(i) for i in range(200)))

    allowed_count = sum(results)
    denied_count = 200 - allowed_count

    assert allowed_count == 10, f"Expected exactly 10 allowed, got {allowed_count}"
    assert denied_count == 190, f"Expected exactly 190 denied, got {denied_count}"
