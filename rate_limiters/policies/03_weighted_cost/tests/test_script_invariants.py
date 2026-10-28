"""Invariant tests against real Redis for weighted GCRA and refund scripts."""

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
async def test_cost_greater_than_burst_is_rejected_permanently(
    repository: RedisRepository,
) -> None:
    """DoD Requirement: cost > burst is rejected permanently (not "retry later")."""
    identity = f"inv_oversized_{int(time.time() * 1000)}"
    burst = 10
    cost = 15  # Impossible request: cost exceeds total burst capacity

    allowed_code, remaining, retry_after, _, _ = await repository.evaluate(
        identity=identity,
        limit=10,
        period=10,
        burst=burst,
        cost=cost,
    )

    # -1 signals permanent rejection (never retryable)
    assert allowed_code == -1
    assert retry_after == 0
    assert remaining == 0


@pytest.mark.asyncio
async def test_refund_returns_unused_cost_and_cannot_exceed_capacity(
    repository: RedisRepository, redis_client: redis.Redis
) -> None:
    """DoD Requirement: Refund script returns unused cost and cannot exceed capacity."""
    identity = f"inv_refund_{int(time.time() * 1000)}"
    limit = 20
    period = 10
    burst = 20

    # 1. Consume 15 units out of 20
    allowed, rem1, _, _, _ = await repository.evaluate(
        identity=identity,
        limit=limit,
        period=period,
        burst=burst,
        cost=15,
    )
    assert allowed == 1
    assert rem1 == 5

    # 2. Refund 10 units (actual work used only 5)
    success, rem2, _ = await repository.refund(
        identity=identity,
        limit=limit,
        period=period,
        burst=burst,
        refund_cost=10,
    )
    assert success == 1
    assert rem2 == 15, f"Expected 15 remaining after refund, got {rem2}"

    # 3. CRITICAL INVARIANT: Over-refunding cannot create free capacity beyond burst!
    now_ms = int(time.time() * 1000)
    # Attempt to refund 500 units on a bucket with max burst 20
    _, rem_capped, tat = await repository.refund(
        identity=identity,
        limit=limit,
        period=period,
        burst=burst,
        refund_cost=500,
        now_ms=now_ms,
    )

    # Must be strictly capped at burst capacity
    assert rem_capped == burst, f"Capacity leaked! Expected {burst}, got {rem_capped}"
    # TAT must not be pushed into the past before now_ms
    assert tat >= now_ms, f"TAT was pulled before clock ({tat} < {now_ms})"


@pytest.mark.asyncio
async def test_mock_llm_estimate_and_settle_workflow(
    repository: RedisRepository,
) -> None:
    """DoD Requirement: Mock 'LLM' endpoint: estimate at start, correct at end."""
    identity = f"inv_llm_{int(time.time() * 1000)}"
    limit = 50
    period = 10
    burst = 50

    # Step 1: Upfront reservation for prompt + max_tokens (e.g. 30 tokens)
    estimated_tokens = 30
    allowed, rem_after_reserve, _, _, _ = await repository.evaluate(
        identity=identity,
        limit=limit,
        period=period,
        burst=burst,
        cost=estimated_tokens,
    )
    assert allowed == 1
    assert rem_after_reserve == 20

    # Step 2: Generation finished; actual usage was only 12 tokens
    actual_tokens = 12
    unused_tokens = estimated_tokens - actual_tokens  # 18 tokens to refund

    # Step 3: Settle difference
    success, rem_final, _ = await repository.refund(
        identity=identity,
        limit=limit,
        period=period,
        burst=burst,
        refund_cost=unused_tokens,
    )
    assert success == 1
    # 20 + 18 = 38 tokens remaining
    assert rem_final == 38, f"Expected 38 tokens after settlement, got {rem_final}"
