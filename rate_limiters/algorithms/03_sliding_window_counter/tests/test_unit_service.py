"""Unit tests for RateLimiterService using a fake repository."""

import math

import pytest
from app.schemas.rule import Rule
from app.services.rate_limiter_service import RateLimiterService


class FakeRepository:
    """In-memory simulation of the sliding window counter algorithm."""

    def __init__(self) -> None:
        self.windows: dict[str, int] = {}  # window_key -> count

    async def evaluate_sliding_counter(
        self,
        identity: str,
        rule_name: str,
        limit: int,
        window_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int, int]:
        window_num = now_ms // window_ms
        window_start_ms = window_num * window_ms

        curr_key = f"{identity}:{rule_name}:swc:{window_num}"
        prev_key = f"{identity}:{rule_name}:swc:{window_num - 1}"

        prev_count = self.windows.get(prev_key, 0)
        curr_count = self.windows.get(curr_key, 0)

        elapsed_ms = now_ms - window_start_ms
        if elapsed_ms < 0:
            elapsed_ms = 0
        elapsed_fraction = elapsed_ms / window_ms
        if elapsed_fraction > 1:
            elapsed_fraction = 1

        weight = 1 - elapsed_fraction
        estimated = math.floor(prev_count * weight + curr_count)

        if estimated < limit:
            self.windows[curr_key] = curr_count + 1
            new_estimated = math.floor(prev_count * weight + curr_count + 1)
            remaining = max(0, limit - new_estimated)
            reset_ms = window_ms - elapsed_ms
            reset_s = math.ceil(max(0, reset_ms) / 1000)
            return (1, remaining, 0, reset_s, estimated, new_estimated)
        else:
            # Denied
            if prev_count > 0 and curr_count < limit:
                needed_fraction = 1 - (limit - curr_count) / prev_count
                if needed_fraction <= 0:
                    retry_after_ms = 0
                else:
                    retry_after_ms = math.ceil(needed_fraction * window_ms)
                retry_after_ms = retry_after_ms - elapsed_ms
                if retry_after_ms < 0:
                    retry_after_ms = 0
            else:
                retry_after_ms = window_ms - elapsed_ms

            retry_after_s = math.ceil(max(0, retry_after_ms) / 1000)
            if retry_after_s < 1:
                retry_after_s = 1

            reset_ms = window_ms - elapsed_ms
            reset_s = math.ceil(max(0, reset_ms) / 1000)
            return (0, 0, retry_after_s, reset_s, estimated, estimated)


@pytest.mark.asyncio
async def test_service_allows_within_limit() -> None:
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:counter", limit=5, period=10)

    # 5 requests at t=2000ms (2s into a 10s window) -> all allowed
    for i in range(5):
        d = await service.evaluate("user:alice", rule, current_time=2.0 + i * 0.001)
        assert d.allowed is True

    # 6th request at t=2.005 -> denied
    d = await service.evaluate("user:alice", rule, current_time=2.005)
    assert d.allowed is False
    assert d.violated_rule == "api:counter"


@pytest.mark.asyncio
async def test_service_blends_windows_correctly() -> None:
    """Tests the approximation formula with previous + current window blending."""
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:blend", limit=100, period=60)

    # Simulate: previous window had 84 requests
    prev_window = 0 // 60000  # Window #0 for t < 60s
    prev_key = f"user:alice:api:blend:swc:{prev_window}"
    repo.windows[prev_key] = 84

    # We are exactly 15 seconds into the current window (t=75.0s = 75000ms)
    # elapsed_fraction = 15000/60000 = 0.25
    # weight = 0.75
    # estimated = floor(84 * 0.75 + 0) = floor(63) = 63
    # So we should be able to make limit - estimated = 37 more requests
    fixed_time = 75.0  # Use a fixed timestamp for all requests

    # Make 36 requests (should all be allowed)
    for i in range(36):
        d = await service.evaluate("user:alice", rule, current_time=fixed_time)
        assert d.allowed is True, f"Request {i + 1} should be allowed"

    # At this point: estimated = floor(84*0.75 + 36) = floor(63 + 36) = 99 < 100
    # One more request should be allowed
    d = await service.evaluate("user:alice", rule, current_time=fixed_time)
    assert d.allowed is True, "Request 37 should be allowed (estimated 99 + 1 = 100)"

    # Now estimated = floor(84*0.75 + 37) = floor(63 + 37) = 100 >= 100 -> denied
    d = await service.evaluate("user:alice", rule, current_time=fixed_time)
    assert d.allowed is False, "Request 38 should be denied"


@pytest.mark.asyncio
async def test_denied_requests_dont_consume() -> None:
    """Denied requests must not increment the counter."""
    repo = FakeRepository()
    service = RateLimiterService(repo)
    rule = Rule(name="api:nocount", limit=3, period=10)

    # Fill up
    for _ in range(3):
        d = await service.evaluate("user:bob", rule, current_time=1.0)
        assert d.allowed is True

    # Hammer with denied requests
    for _ in range(10):
        d = await service.evaluate("user:bob", rule, current_time=1.5)
        assert d.allowed is False

    # Check counter value: should still be 3, not 13
    window_num = 1000 // 10000  # = 0
    key = f"user:bob:api:nocount:swc:{window_num}"
    assert repo.windows.get(key, 0) == 3
