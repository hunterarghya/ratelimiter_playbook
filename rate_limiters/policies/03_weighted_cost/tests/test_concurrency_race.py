"""Concurrency test: 200 parallel requests with weighted cost against Redis."""

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
async def test_200_parallel_weighted_requests_allows_exact_capacity(
    repository: RedisRepository,
) -> None:
    identity = f"race_weighted_{int(time.time() * 1000)}"
    burst = 20
    cost_per_call = 2  # Each call consumes 2 tokens -> exactly 10 calls can succeed

    async def single_call() -> int:
        allowed, _, _, _, _ = await repository.evaluate(
            identity=identity,
            limit=20,
            period=10_000,
            burst=burst,
            cost=cost_per_call,
        )
        return allowed

    # Fire 200 coroutines concurrently
    results = await asyncio.gather(*(single_call() for _ in range(200)))

    allowed_count = sum(1 for r in results if r == 1)
    denied_count = sum(1 for r in results if r == 0)

    assert allowed_count == 10, f"Expected exactly 10 allowed (10*2=20 burst), got {allowed_count}"
    assert denied_count == 190, f"Expected 190 denied, got {denied_count}"
