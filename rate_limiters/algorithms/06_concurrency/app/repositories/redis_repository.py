"""Redis repository executing concurrency lease acquisition and release."""

import time
from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_path = Path(__file__).resolve().parent.parent / "lua" / "acquire_lease.lua"
        self._script_content = lua_path.read_text(encoding="utf-8")
        self._script = self.redis.register_script(self._script_content)

    async def acquire_lease(
        self,
        identity: str,
        rule_name: str,
        limit: int,
        lease_id: str,
        lease_ttl_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        """Atomically cleans expired leases, counts active leases, and acquires if below limit.

        Returns: (allowed, remaining, retry_after_seconds, reset_seconds, limit)
        """
        key = f"rl:{{{identity}}}:{rule_name}:leases"
        res = await self._script(
            keys=[key],
            args=[
                str(limit),
                lease_id,
                str(lease_ttl_ms),
                str(now_ms),
            ],
        )
        data = cast(list[int], res)
        return data[0], data[1], data[2], data[3], data[4]

    async def release_lease(
        self,
        identity: str,
        rule_name: str,
        lease_id: str,
    ) -> bool:
        """Releases a concurrency lease.

        Rule 1: A single ZREM is a single atomic Redis command executed directly from client.
        """
        key = f"rl:{{{identity}}}:{rule_name}:leases"
        removed_count = await self.redis.zrem(key, lease_id)
        return bool(removed_count > 0)

    async def get_state(self, pattern: str = "rl:*") -> dict[str, Any]:
        """Inspects all matching rate limiter keys in Redis."""
        keys = await self.redis.keys(pattern)
        now_ms = int(time.time() * 1000)
        state: dict[str, Any] = {}

        for k in keys:
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            k_type = await self.redis.type(k)
            k_type_str = k_type.decode() if isinstance(k_type, bytes) else str(k_type)
            ttl = await self.redis.ttl(k)

            if k_type_str == "zset":
                raw_members = await self.redis.zrange(k, 0, -1, withscores=True)
                members = cast(list[tuple[Any, float]], raw_members)
                active_leases = []
                for member, score in members:
                    m_str = member.decode() if isinstance(member, bytes) else str(member)
                    exp_ms = int(score)
                    exp_in_sec = round((exp_ms - now_ms) / 1000.0, 2)
                    active_leases.append(
                        {
                            "lease_id": m_str,
                            "expires_at_ms": exp_ms,
                            "expires_in_seconds": exp_in_sec,
                        }
                    )
                state[k_str] = {
                    "type": "zset",
                    "ttl": ttl,
                    "active_leases_count": len(active_leases),
                    "leases": active_leases,
                }
            else:
                state[k_str] = {"type": k_type_str, "ttl": ttl}

        return state

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False
