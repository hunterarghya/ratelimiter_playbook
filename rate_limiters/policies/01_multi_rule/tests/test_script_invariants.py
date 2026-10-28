"""Invariant tests against real Redis for multi-rule atomic Lua script."""

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
    client = redis.from_url(url)
    yield client
    await client.aclose()


@pytest.fixture
async def repository(redis_client: redis.Redis) -> RedisRepository:
    return RedisRepository(redis_client)


@pytest.mark.asyncio
async def test_denied_hourly_rule_does_not_consume_per_second_rule(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    """DoD Requirement: Request denied by the hourly rule does not consume the per-second rule.

    Response names the violated rule. Retry-After is the max across violated rules.
    """
    identity = f"inv_multi_{int(time.time() * 1000)}"
    rule_sec = Rule(name="sec_rule", limit=10, period=1, burst=10)
    rule_hour = Rule(name="hour_rule", limit=2, period=3600, burst=2)
    rules = [rule_sec, rule_hour]

    key_sec = f"rl:{{{identity}}}:sec_rule:gcra"
    key_hour = f"rl:{{{identity}}}:hour_rule:gcra"

    # Call 1 & 2 pass both rules
    a1, _, _, _, _, _ = await repository.evaluate_multi_rule(identity, rules)
    a2, _, _, _, _, _ = await repository.evaluate_multi_rule(identity, rules)
    assert a1 == 1 and a2 == 1

    # Record exact TATs in Redis before call 3
    tat_sec_before = await redis_client.get(key_sec)
    tat_hour_before = await redis_client.get(key_hour)
    assert tat_sec_before is not None
    assert tat_hour_before is not None

    # Call 3: sec_rule has 8 tokens left, but hour_rule is exhausted!
    allowed, remaining, retry_after, _, _, violated = await repository.evaluate_multi_rule(
        identity, rules
    )

    # 1. Must be denied
    assert allowed == 0
    # 2. Must name the violated rule
    assert violated == "hour_rule"
    # 3. Retry-After reflects the hourly rule wait
    assert retry_after >= 1700

    # 4. CRITICAL INVARIANT: sec_rule was NOT charged in Redis!
    tat_sec_after = await redis_client.get(key_sec)
    tat_hour_after = await redis_client.get(key_hour)

    assert tat_sec_after == tat_sec_before, (
        f"Quota burn detected! sec_rule was charged ({tat_sec_before!r} -> {tat_sec_after!r})"
    )
    assert tat_hour_after == tat_hour_before


@pytest.mark.asyncio
async def test_idle_keys_have_ttl(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    identity = f"inv_ttl_{int(time.time() * 1000)}"
    rules = [
        Rule(name="r1", limit=5, period=1, burst=5),
        Rule(name="r2", limit=50, period=60, burst=50),
    ]

    await repository.evaluate_multi_rule(identity, rules)

    for r in rules:
        key = f"rl:{{{identity}}}:{r.name}:gcra"
        ttl = await redis_client.ttl(key)
        assert ttl > 0, f"Expected key {key} to have positive TTL"
