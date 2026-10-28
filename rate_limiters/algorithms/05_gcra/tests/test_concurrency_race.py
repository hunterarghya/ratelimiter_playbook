"""Concurrency test: 200 parallel requests against limit N using GCRA Lua script."""

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
    burst = 10
    # Very slow refill: 1 request every 10,000 seconds
    t_ms = 10_000_000.0
    tau_ms = t_ms * burst

    async def single_call() -> int:
        allowed, _, _, _, _ = await repository.evaluate_gcra(
            identity=identity,
            rule_name=rule_name,
            t_ms=t_ms,
            tau_ms=tau_ms,
            burst=burst,
        )
        return allowed

    # Fire 200 coroutines concurrently
    results = await asyncio.gather(*(single_call() for _ in range(200)))

    allowed_count = sum(results)
    denied_count = 200 - allowed_count

    assert allowed_count == 10, f"Expected exactly 10 allowed, got {allowed_count}"
    assert denied_count == 190, f"Expected exactly 190 denied, got {denied_count}"
