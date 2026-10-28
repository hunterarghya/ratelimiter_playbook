"""Redis repository executing sliding window counter Lua script."""

from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_path = (
            Path(__file__).resolve().parent.parent / "lua" / "sliding_window_counter.lua"
        )
        self._script_content = lua_path.read_text(encoding="utf-8")
        self._script = self.redis.register_script(self._script_content)

    async def evaluate_sliding_counter(
        self,
        identity: str,
        rule_name: str,
        limit: int,
        window_ms: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int, int]:
        """Calls sliding_window_counter.lua inside Redis via register_script (EVALSHA).

        Computes the current and previous window keys based on now_ms and window_ms.
        Returns tuple of (allowed, remaining, retry_after, reset,
        estimated_before, estimated_after).
        """
        # Determine now_ms for key derivation (use a rough value; Lua will use Redis TIME if 0)
        effective_now_ms = now_ms
        if effective_now_ms <= 0:
            import time

            effective_now_ms = int(time.time() * 1000)

        # Window number and key derivation
        window_num = effective_now_ms // window_ms
        window_start_ms = window_num * window_ms

        curr_key = f"rl:{{{identity}}}:{rule_name}:swc:{window_num}"
        prev_key = f"rl:{{{identity}}}:{rule_name}:swc:{window_num - 1}"

        keys = [curr_key, prev_key]
        args = [str(limit), str(window_ms), str(now_ms), str(window_start_ms)]

        res = await self._script(keys=keys, args=args)
        res_list = cast(list[int], res)
        return (
            int(res_list[0]),
            int(res_list[1]),
            int(res_list[2]),
            int(res_list[3]),
            int(res_list[4]),
            int(res_list[5]),
        )

    async def get_state(self, key_pattern: str) -> dict[str, Any]:
        """Fetches raw counter values and TTLs for debugging."""
        keys = await self.redis.keys(key_pattern)
        state: dict[str, Any] = {}
        for k in keys:
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            ttl = await self.redis.ttl(k_str)
            k_type = await self.redis.type(k_str)
            k_type_str = k_type.decode() if isinstance(k_type, bytes) else str(k_type)

            if k_type_str == "string":
                raw_val = await self.redis.get(k_str)
                val = raw_val.decode() if isinstance(raw_val, bytes) else str(raw_val)
                state[k_str] = {
                    "type": "string",
                    "ttl": ttl,
                    "value": val,
                }
            elif k_type_str == "zset":
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
