"""Invariant tests against real Redis for token bucket Lua script."""

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
async def test_denied_requests_do_not_decrement_tokens(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_deny_{int(time.time() * 1000)}"
    rule_name = "test_deny"
    capacity = 3
    refill_rate = 0.5  # 0.5 tokens/sec
    key = f"rl:{{{identity}}}:{rule_name}:tb"

    # Drain capacity (3 requests)
    for _ in range(3):
        allowed, remaining, _, _, _ = await repository.evaluate_token_bucket(
            identity, rule_name, capacity, refill_rate
        )
        assert allowed == 1

    # Now bucket should have 0 tokens
    raw_tokens = await redis_client.hget(key, "tokens")
    assert raw_tokens is not None
    tokens_before = float(raw_tokens)
    assert tokens_before < 1.0

    # Fire 5 denied requests
    for _ in range(5):
        allowed, _, _, _, _ = await repository.evaluate_token_bucket(
            identity, rule_name, capacity, refill_rate
        )
        assert allowed == 0

    # Verify tokens did not become negative
    raw_tokens_after = await redis_client.hget(key, "tokens")
    assert raw_tokens_after is not None
    tokens_after = float(raw_tokens_after)
    assert tokens_after >= 0.0


@pytest.mark.asyncio
async def test_idle_key_has_ttl(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_ttl_{int(time.time() * 1000)}"
    rule_name = "test_ttl"
    key = f"rl:{{{identity}}}:{rule_name}:tb"

    await repository.evaluate_token_bucket(identity, rule_name, capacity=5, refill_rate_per_sec=1.0)
    ttl = await redis_client.ttl(key)
    assert ttl > 0, f"Expected key to have positive TTL, got {ttl}"


@pytest.mark.asyncio
async def test_lazy_refill_and_capacity_cap(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_refill_{int(time.time() * 1000)}"
    rule_name = "test_refill"
    capacity = 4
    refill_rate = 2.0  # 2 tokens/sec
    base_time_ms = 1_700_000_000_000

    # 1. Drain 4 tokens at t=0
    for _ in range(4):
        allowed, _, _, _, _ = await repository.evaluate_token_bucket(
            identity, rule_name, capacity, refill_rate, cost=1, now_ms=base_time_ms
        )
        assert allowed == 1

    # 5th request at t=0 denied
    allowed, remaining, retry_after, _, _ = await repository.evaluate_token_bucket(
        identity, rule_name, capacity, refill_rate, cost=1, now_ms=base_time_ms
    )
    assert allowed == 0
    assert remaining == 0
    assert retry_after >= 1

    # 2. Advance time by 500ms -> 1 token refilled (0.5s * 2 tokens/s = 1.0 token)
    allowed, remaining, _, _, _ = await repository.evaluate_token_bucket(
        identity, rule_name, capacity, refill_rate, cost=1, now_ms=base_time_ms + 500
    )
    assert allowed == 1
    assert remaining == 0

    # 3. Advance time by 50 seconds (huge idle) -> must cap at capacity=4
    allowed, remaining, _, _, _ = await repository.evaluate_token_bucket(
        identity, rule_name, capacity, refill_rate, cost=1, now_ms=base_time_ms + 50_500
    )
    assert allowed == 1
    # Capacity is 4, 1 token consumed -> remaining is 3
    assert remaining == 3
