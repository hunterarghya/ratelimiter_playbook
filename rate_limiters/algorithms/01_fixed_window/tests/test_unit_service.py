"""Unit tests for RateLimiterService using a fake in-memory repository."""

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


class FakeRepository:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def increment_and_expire(self, key: str, window_seconds: int) -> tuple[int, int]:
        current = self.counters.get(key, 0) + 1
        self.counters[key] = current
        if key not in self.ttls:
            self.ttls[key] = window_seconds
        return current, self.ttls[key]


@pytest.mark.asyncio
async def test_service_allows_requests_within_limit() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:sec", limit=3, period=10)

    # 1st request
    d1 = await service.evaluate("user:alice", rule, current_time=100.0)
    assert d1.allowed is True
    assert d1.remaining == 2
    assert d1.retry_after == 0
    assert d1.violated_rule is None

    # 2nd request
    d2 = await service.evaluate("user:alice", rule, current_time=100.1)
    assert d2.allowed is True
    assert d2.remaining == 1

    # 3rd request (exact limit)
    d3 = await service.evaluate("user:alice", rule, current_time=100.2)
    assert d3.allowed is True
    assert d3.remaining == 0


@pytest.mark.asyncio
async def test_service_denies_requests_over_limit() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:sec", limit=2, period=10)

    # Use up limit
    await service.evaluate("user:alice", rule, current_time=100.0)
    await service.evaluate("user:alice", rule, current_time=101.0)

    # Exceeding request
    d3 = await service.evaluate("user:alice", rule, current_time=102.0)
    assert d3.allowed is False
    assert d3.remaining == 0
    assert d3.retry_after == 8  # (100 // 10 + 1) * 10 - 102 = 110 - 102 = 8
    assert d3.violated_rule == "api:sec"


@pytest.mark.asyncio
async def test_service_resets_on_new_window() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:sec", limit=2, period=10)

    # Window 10 (t=100..109)
    await service.evaluate("user:alice", rule, current_time=105.0)
    await service.evaluate("user:alice", rule, current_time=108.0)
    d_denied = await service.evaluate("user:alice", rule, current_time=109.0)
    assert d_denied.allowed is False

    # Window 11 starts at t=110
    d_new_window = await service.evaluate("user:alice", rule, current_time=110.0)
    assert d_new_window.allowed is True
    assert d_new_window.remaining == 1


def test_key_construction_uses_identity_hash_tag() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    key = service.build_key("user:42", "login:min", 15)
    assert key == "rl:{user:42}:login:min:fw:15"
    assert "{user:42}" in key
