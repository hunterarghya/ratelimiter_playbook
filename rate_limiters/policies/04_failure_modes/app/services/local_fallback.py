"""Per-process in-memory rate limiter used when Redis is unavailable.

Uses a simple token-bucket with time-based refill.
This is intentionally approximate: each app instance enforces independently,
so total allowed traffic = fallback_limit * num_instances.
"""

import threading
import time


class LocalFallbackLimiter:
    """Thread-safe per-process token bucket limiter."""

    def __init__(self, limit: int, period: float, multiplier: float = 1.5) -> None:
        self._limit = limit
        self._period = period
        # Safety multiplier: restrict per-process capacity below global limit
        # because we can't coordinate across instances.
        # e.g., limit=100 across 4 instances → each gets ~100/4*1.5 = 37
        self._capacity = max(1, int(limit * multiplier))
        self._tokens = float(self._capacity)
        self._refill_rate = self._capacity / period  # tokens per second
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def try_acquire(self, cost: int = 1) -> tuple[bool, int]:
        """Attempts to consume `cost` tokens.

        Returns: (allowed, remaining_tokens)
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._last_refill = now

            # Refill tokens based on elapsed time
            self._tokens = min(
                float(self._capacity),
                self._tokens + elapsed * self._refill_rate,
            )

            if self._tokens >= cost:
                self._tokens -= cost
                return True, int(self._tokens)
            return False, 0

    def reset(self) -> None:
        """Resets the fallback limiter to full capacity."""
        with self._lock:
            self._tokens = float(self._capacity)
            self._last_refill = time.monotonic()
