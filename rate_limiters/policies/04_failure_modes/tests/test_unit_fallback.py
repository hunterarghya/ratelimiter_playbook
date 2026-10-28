"""Unit tests for the local in-memory fallback rate limiter."""

import time

from app.services.local_fallback import LocalFallbackLimiter


def test_local_fallback_initial_capacity() -> None:
    limiter = LocalFallbackLimiter(limit=5, period=10.0, multiplier=1.0)
    assert limiter.capacity == 5

    # Consume all 5 tokens
    for _ in range(5):
        allowed, remaining = limiter.try_acquire(cost=1)
        assert allowed is True

    # 6th request should fail
    allowed, remaining = limiter.try_acquire(cost=1)
    assert allowed is False
    assert remaining == 0


def test_local_fallback_refill() -> None:
    # 2 tokens per 0.2 seconds = 10 tokens / sec
    limiter = LocalFallbackLimiter(limit=2, period=0.2, multiplier=1.0)
    allowed, _ = limiter.try_acquire(cost=2)
    assert allowed is True

    # Now empty
    allowed, _ = limiter.try_acquire(cost=1)
    assert allowed is False

    # Sleep for refill
    time.sleep(0.25)
    allowed, remaining = limiter.try_acquire(cost=1)
    assert allowed is True
    assert remaining >= 0


def test_local_fallback_reset() -> None:
    limiter = LocalFallbackLimiter(limit=3, period=10.0, multiplier=1.0)
    for _ in range(3):
        limiter.try_acquire()
    assert limiter.try_acquire()[0] is False

    limiter.reset()
    assert limiter.try_acquire()[0] is True
