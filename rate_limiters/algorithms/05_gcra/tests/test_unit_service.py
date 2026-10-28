"""Unit tests for RateLimiterService using an in-memory FakeRepository for GCRA."""

import math

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


class FakeRepository:
    """In-memory simulation of the GCRA Lua script."""

    def __init__(self) -> None:
        self.tats: dict[str, int] = {}
        self.simulated_time_ms: int = 1_000_000

    async def evaluate_gcra(
        self,
        identity: str,
        rule_name: str,
        t_ms: float,
        tau_ms: float,
        burst: int,
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        ts = now_ms if now_ms > 0 else self.simulated_time_ms
        key = f"rl:{{{identity}}}:{rule_name}:gcra"

        tat = self.tats.get(key, 0)
        base_tat = max(tat, ts)
        increment_ms = t_ms * cost
        new_tat = int(base_tat + increment_ms)
        earliest_allowed = new_tat - tau_ms

        if ts < earliest_allowed:
            allowed = 0
            deficit_ms = earliest_allowed - ts
            retry_after_sec = math.ceil(deficit_ms / 1000.0)
            # Denied requests consume nothing: TAT remains unchanged
        else:
            allowed = 1
            tat = new_tat
            self.tats[key] = tat
            retry_after_sec = 0

        reset_ms = max(0, tat - ts)
        reset_sec = math.ceil(reset_ms / 1000.0)

        available_time = max(0.0, (ts + tau_ms) - tat)
        remaining = min(burst, math.floor(available_time / t_ms))

        return (
            allowed,
            remaining,
            retry_after_sec,
            reset_sec,
            burst,
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

    # 5th immediate call exceeds burst tolerance
    decision = await service.evaluate("alice", rule)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after >= 1


@pytest.mark.asyncio
async def test_service_recovers_after_emission_interval() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=4)

    # Drain burst (4 requests)
    for _ in range(4):
        await service.evaluate("alice", rule)

    # Advance time by 500ms (1 emission interval: 1000ms / 2)
    repo.simulated_time_ms += 500

    decision = await service.evaluate("alice", rule)
    assert decision.allowed is True
    assert decision.remaining == 0

    # Another immediate call fails
    decision = await service.evaluate("alice", rule)
    assert decision.allowed is False


@pytest.mark.asyncio
async def test_service_idle_does_not_hoard() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=4)

    # Make 2 requests
    await service.evaluate("alice", rule)
    await service.evaluate("alice", rule)

    # Wait 100 seconds
    repo.simulated_time_ms += 100_000

    # Next call allows and caps remaining at burst - 1 = 3
    decision = await service.evaluate("alice", rule)
    assert decision.allowed is True
    assert decision.remaining == 3


@pytest.mark.asyncio
async def test_denied_requests_do_not_advance_tat() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api", limit=2, period=1, burst=2)

    # Drain burst
    await service.evaluate("alice", rule)
    await service.evaluate("alice", rule)

    key = "rl:{alice}:api:gcra"
    tat_before = repo.tats[key]

    # Multiple denied calls
    for _ in range(5):
        decision = await service.evaluate("alice", rule)
        assert decision.allowed is False

    # TAT must remain identical
    assert repo.tats[key] == tat_before
