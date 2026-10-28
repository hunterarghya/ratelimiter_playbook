"""Concurrency test: 200 parallel requests against limit N using Lua script."""

import asyncio
import os
import time
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis
from app.repositories.redis_repository import RedisRepository
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


@pytest.fixture
async def redis_client() -> AsyncIterator[redis.Redis]:
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client = redis.from_url(url, max_connections=300, decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_200_parallel_requests_allows_exact_limit(redis_client: redis.Redis) -> None:
    repo = RedisRepository(redis_client)
    service = RateLimiterService(repo)
    limit = 10
    rule = Rule(name="race_test", limit=limit, period=60)
    identity = f"user:concurrency_{int(time.time()*1000)}"

    # Use a fixed time so all requests land in the same window
    fixed_time = 1000.0

    async def single_call() -> bool:
        decision = await service.evaluate(identity, rule, current_time=fixed_time)
        return decision.allowed

    # 200 concurrent requests fired simultaneously
    tasks = [single_call() for _ in range(200)]
    results = await asyncio.gather(*tasks)

    allowed = sum(1 for r in results if r is True)
    denied = sum(1 for r in results if r is False)

    assert allowed == limit, f"Expected exactly {limit} allowed, got {allowed}"
    assert denied == 200 - limit, f"Expected {200 - limit} denied, got {denied}"
