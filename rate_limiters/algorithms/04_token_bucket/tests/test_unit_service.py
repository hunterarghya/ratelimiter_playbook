"""Unit tests for RateLimiterService using an in-memory FakeRepository."""

import math
from dataclasses import dataclass

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


@dataclass
class BucketState:
    tokens: float
    last_ts_ms: int


class FakeRepository:
    """In-memory simulation of the token bucket Lua script."""

    def __init__(self) -> None:
        self.buckets: dict[str, BucketState] = {}
        self.simulated_time_ms: int = 1_000_000

    async def evaluate_token_bucket(
        self,
        identity: str,
        rule_name: str,
        capacity: int,
        refill_rate_per_sec: float,
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        ts = now_ms if now_ms > 0 else self.simulated_time_ms
        key = f"rl:{{{identity}}}:{rule_name}:tb"

        state = self.buckets.get(key)
        if state is None:
            tokens = float(capacity)
        else:
            elapsed_ms = max(0, ts - state.last_ts_ms)
            refilled = (elapsed_ms / 1000.0) * refill_rate_per_sec
            tokens = min(float(capacity), state.tokens + refilled)

        if tokens >= cost:
            allowed = 1
            tokens -= cost
            self.buckets[key] = BucketState(tokens=tokens, last_ts_ms=ts)
            retry_after_sec = 0.0
        else:
            allowed = 0
            # Denied requests consume nothing
            self.buckets[key] = BucketState(tokens=tokens, last_ts_ms=ts)
            deficit = cost - tokens
            retry_after_sec = deficit / refill_rate_per_sec

        missing = max(0.0, capacity - tokens)
        reset_sec = missing / refill_rate_per_sec

        return (
            allowed,
            math.floor(tokens),
            math.ceil(retry_after_sec),
            math.ceil(reset_sec),
            capacity,
        )


@pytest.mark.asyncio
async def test_service_allows_within_burst_capacity() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=4)

    # 4 immediate calls within burst
    for i in range(4):
        decision = await service.evaluate("alice", rule)
        assert decision.allowed is True
        assert decision.remaining == 3 - i

    # 5th immediate call exceeds burst capacity
    decision = await service.evaluate("alice", rule)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after >= 1


@pytest.mark.asyncio
async def test_service_refills_tokens_over_time() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=4)

    # Consume all 4 tokens
    for _ in range(4):
        await service.evaluate("alice", rule)

    # Advance simulated time by 500ms -> 1 token refilled (2 tokens/sec * 0.5s = 1)
    repo.simulated_time_ms += 500

    decision = await service.evaluate("alice", rule)
    assert decision.allowed is True
    assert decision.remaining == 0

    # Another immediate call fails
    decision = await service.evaluate("alice", rule)
    assert decision.allowed is False


@pytest.mark.asyncio
async def test_service_caps_at_maximum_burst() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=4)

    # Consume 2 tokens
    await service.evaluate("alice", rule)
    await service.evaluate("alice", rule)

    # Wait for 100 seconds (far longer than refill time)
    repo.simulated_time_ms += 100_000

    # Bucket should not hoard tokens beyond capacity=4
    decision = await service.evaluate("alice", rule)
    assert decision.allowed is True
    # Capacity was 4, consumed 1, remaining is 3
    assert decision.remaining == 3


@pytest.mark.asyncio
async def test_denied_requests_dont_consume_tokens() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=2)

    # Drain bucket
    await service.evaluate("alice", rule)
    await service.evaluate("alice", rule)

    # Multiple denied calls
    for _ in range(5):
        decision = await service.evaluate("alice", rule)
        assert decision.allowed is False

    # Key state still has >= 0 tokens, never negative
    key = "rl:{alice}:api:tb"
    assert repo.buckets[key].tokens >= 0.0
