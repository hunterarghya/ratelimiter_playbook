"""Redis repository for fixed window rate limiting."""

from typing import Any

import redis.asyncio as redis


class RedisRepository:
    def __init__(self, client: redis.Redis) -> None:
        self.redis = client

    async def increment_and_expire(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Atomically increments the window counter and sets TTL on first creation (NX).

        Returns: (count, ttl)
        """
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            results = await pipe.execute()

        count = int(results[0])
        ttl = int(await self.redis.ttl(key))
        return count, ttl

    async def get_state(self, key_pattern: str) -> dict[str, Any]:
        """Fetches raw keys, types, and values matching pattern for debug."""
        keys = await self.redis.keys(key_pattern)
        state: dict[str, Any] = {}
        for k in keys:
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            val = await self.redis.get(k_str)
            ttl = await self.redis.ttl(k_str)
            val_str = val.decode() if isinstance(val, bytes) else str(val)
            state[k_str] = {"value": val_str, "ttl": ttl}
        return state

    async def ping(self) -> bool:
        """Pings Redis to check connectivity."""
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False
