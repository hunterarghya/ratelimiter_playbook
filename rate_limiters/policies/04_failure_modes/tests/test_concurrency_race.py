"""Concurrency test: 200 parallel requests against Redis repository using GCRA Lua."""

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
async def test_200_parallel_requests_allows_exact_burst(
    repository: RedisRepository,
) -> None:
    identity = f"race_failure_{int(time.time() * 1000)}"
    burst = 10
    limit = 10
    period = 10.0
    t_ms = (period * 1000.0) / float(limit)
    tau_ms = t_ms * float(burst)

    async def single_call() -> int:
        allowed, _, _, _, _ = await repository.evaluate(
            identity=identity,
            rule_name="std",
            t_ms=t_ms,
            tau_ms=tau_ms,
            burst=burst,
            cost=1,
        )
        return allowed

    # Fire 200 coroutines concurrently
    results = await asyncio.gather(*(single_call() for _ in range(200)))

    allowed_count = sum(1 for r in results if r == 1)
    denied_count = sum(1 for r in results if r == 0)

    assert allowed_count == burst, f"Expected exactly {burst} allowed, got {allowed_count}"
    assert denied_count == (200 - burst), f"Expected {200 - burst} denied, got {denied_count}"
