"""Concurrency test: 200 parallel requests against identity strategies limiter."""

import asyncio
import os
import time
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis
from app.repositories.redis_repository import RedisRepository
from app.schemas.rule import Rule


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
    identity = f"race_{int(time.time() * 1000)}"
    rule = Rule(name="race_burst", limit=10, period=10_000, burst=10)
    targets = [(identity, rule)]

    async def single_call() -> int:
        allowed, _, _, _, _, _ = await repository.evaluate_rules(targets)
        return allowed

    # Fire 200 coroutines concurrently
    results = await asyncio.gather(*(single_call() for _ in range(200)))

    allowed_count = sum(results)
    denied_count = 200 - allowed_count

    assert allowed_count == 10, f"Expected exactly 10 allowed, got {allowed_count}"
    assert denied_count == 190, f"Expected exactly 190 denied, got {denied_count}"
