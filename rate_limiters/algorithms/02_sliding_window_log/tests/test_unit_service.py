"""Unit tests for RateLimiterService using a fake repository."""

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


class FakeRepository:
    def __init__(self) -> None:
        self.log: list[float] = []

    async def evaluate_sliding_log(
        self,
        key: str,
        limit: int,
        window_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int]:
        now = now_ms / 1000.0
        window_s = window_ms / 1000.0
        clear_before = now - window_s
        self.log = [ts for ts in self.log if ts > clear_before]

        if len(self.log) < limit:
            self.log.append(now)
            remaining = limit - len(self.log)
            return (1, remaining, 0, int(window_s))
        else:
            oldest = self.log[0] if self.log else now
            retry_after = max(1, int((oldest + window_s) - now))
            return (0, 0, retry_after, retry_after)


@pytest.mark.asyncio
async def test_service_allows_within_sliding_window() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:login", limit=2, period=10)

    d1 = await service.evaluate("user:alice", rule, current_time=100.0)
    assert d1.allowed is True
    assert d1.remaining == 1
    assert d1.retry_after == 0

    d2 = await service.evaluate("user:alice", rule, current_time=102.0)
    assert d2.allowed is True
    assert d2.remaining == 0

    # 3rd request inside window denied
    d3 = await service.evaluate("user:alice", rule, current_time=104.0)
    assert d3.allowed is False
    assert d3.remaining == 0
    assert d3.retry_after == 6  # oldest was 100.0 + 10 - 104 = 6
    assert d3.violated_rule == "api:login"


@pytest.mark.asyncio
async def test_service_slides_window_smoothly() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:login", limit=2, period=10)

    # Two requests at t=100 and t=102
    await service.evaluate("user:alice", rule, current_time=100.0)
    await service.evaluate("user:alice", rule, current_time=102.0)

    # At t=109 (both still inside 10s window) -> denied
    d_denied = await service.evaluate("user:alice", rule, current_time=109.0)
    assert d_denied.allowed is False

    # At t=110.1 (t=100 has dropped out of [100.1, 110.1]) -> allowed!
    d_allowed = await service.evaluate("user:alice", rule, current_time=110.1)
    assert d_allowed.allowed is True
    assert d_allowed.remaining == 0  # 102.0 and 110.1 are active
