"""Redis repository executing sliding window log Lua script."""

from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_path = Path(__file__).resolve().parent.parent / "lua" / "sliding_window_log.lua"
        self._script_content = lua_path.read_text(encoding="utf-8")
        self._script = self.redis.register_script(self._script_content)

    async def evaluate_sliding_log(
        self,
        key: str,
        limit: int,
        window_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int]:
        """Calls sliding_window_log.lua inside Redis via register_script (EVALSHA).

        Returns tuple of (allowed, remaining, retry_after, reset).
        """
        keys = [key]
        args = [str(limit), str(window_ms), str(now_ms)]

        res = await self._script(keys=keys, args=args)
        res_list = cast(list[int], res)
        return (
            int(res_list[0]),
            int(res_list[1]),
            int(res_list[2]),
            int(res_list[3]),
        )

    async def get_state(self, key_pattern: str) -> dict[str, Any]:
        """Fetches raw ZSET entries and TTL for debugging."""
        keys = await self.redis.keys(key_pattern)
        state: dict[str, Any] = {}
        for k in keys:
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            ttl = await self.redis.ttl(k_str)
            k_type = await self.redis.type(k_str)
            k_type_str = k_type.decode() if isinstance(k_type, bytes) else str(k_type)

            if k_type_str == "zset":
                raw_entries = await self.redis.zrange(k_str, 0, -1, withscores=True)
                entries = cast(list[tuple[Any, float]], raw_entries)
                formatted_entries = [
                    {"member": m.decode() if isinstance(m, bytes) else str(m), "score": s}
                    for m, s in entries
                ]
                state[k_str] = {
                    "type": "zset",
                    "ttl": ttl,
                    "entries_count": len(formatted_entries),
                    "entries": formatted_entries,
                }
            else:
                state[k_str] = {"type": k_type_str, "ttl": ttl}

        return state

    async def ping(self) -> bool:
        """Pings Redis to check connectivity."""
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False
