"""Invariant tests against real Redis for identity GCRA Lua script."""

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
async def test_identity_gcra_multi_target_all_or_nothing(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    """When evaluating multiple identities (e.g. IP + User), if one fails, neither consumes."""
    ip_id = f"ip_test_{int(time.time() * 1000)}"
    user_id = f"user_test_{int(time.time() * 1000)}"

    ip_rule = Rule(name="ip_limit", limit=10, period=10, burst=10)
    user_rule = Rule(name="user_limit", limit=2, period=10, burst=2)

    key_ip = f"rl:{{{ip_id}}}:ip_limit:gcra"
    key_user = f"rl:{{{user_id}}}:user_limit:gcra"

    targets = [(ip_id, ip_rule), (user_id, user_rule)]

    # 1 & 2 succeed
    a1, _, _, _, _, _ = await repository.evaluate_rules(targets)
    a2, _, _, _, _, _ = await repository.evaluate_rules(targets)
    assert a1 == 1 and a2 == 1

    tat_ip_before = await redis_client.get(key_ip)
    tat_user_before = await redis_client.get(key_user)
    assert tat_ip_before is not None
    assert tat_user_before is not None

    # Call 3: user quota is exhausted (limit=2), but IP has 8 remaining!
    allowed, _, retry_after, _, _, violated = await repository.evaluate_rules(targets)

    assert allowed == 0
    assert violated == f"{user_id}:user_limit"
    assert retry_after > 0

    # Ensure IP quota was NOT burned
    tat_ip_after = await redis_client.get(key_ip)
    tat_user_after = await redis_client.get(key_user)
    assert tat_ip_after == tat_ip_before
    assert tat_user_after == tat_user_before


@pytest.mark.asyncio
async def test_anonymous_to_authenticated_transition(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    """DoD Requirement: Test for anonymous -> authenticated transition.

    Anonymous user at shared IP exhausts anonymous IP quota.
    Once authenticated, user attaches their user ID which grants user-tier quota.
    """
    shared_ip = f"shared_nat_{int(time.time() * 1000)}"
    user_alice = f"user_alice_{int(time.time() * 1000)}"

    anon_rule = Rule(name="anon", limit=3, period=10, burst=3)
    user_rule = Rule(name="auth", limit=10, period=10, burst=10)

    # 1. Anonymous requests: evaluated strictly against anonymous IP quota
    anon_targets = [(shared_ip, anon_rule)]
    for _ in range(3):
        allowed, _, _, _, _, _ = await repository.evaluate_rules(anon_targets)
        assert allowed == 1

    # 4th anonymous request is blocked by anonymous IP quota
    allowed, _, _, _, _, violated = await repository.evaluate_rules(anon_targets)
    assert allowed == 0
    assert violated == f"{shared_ip}:anon"

    # 2. User logs in as Alice. Authenticated route tracks user_rule.
    # Alice has fresh user quota even though anonymous quota on shared NAT is exhausted!
    auth_targets = [(user_alice, user_rule)]
    allowed_auth, rem_auth, _, _, _, _ = await repository.evaluate_rules(auth_targets)
    assert allowed_auth == 1
    assert rem_auth == 9
