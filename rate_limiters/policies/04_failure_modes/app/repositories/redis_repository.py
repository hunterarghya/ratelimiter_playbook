"""Redis repository executing GCRA Lua script for failure modes policy."""

import time
from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_path = Path(__file__).resolve().parent.parent / "lua" / "gcra.lua"
        self._script_content = lua_path.read_text(encoding="utf-8")
        self._script = self.redis.register_script(self._script_content)

    async def evaluate(
        self,
        identity: str,
        rule_name: str,
        t_ms: float,
        tau_ms: float,
        burst: int,
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        """Evaluates GCRA rate limit atomically in Redis via Lua.

        Returns: (allowed, remaining, retry_after, reset, burst)
        """
        key = f"rl:{{{identity}}}:{rule_name}:gcra"
        res = await self._script(
            keys=[key],
            args=[str(t_ms), str(tau_ms), str(cost), str(burst), str(now_ms)],
        )
        data = cast(list[int], res)
        return data[0], data[1], data[2], data[3], data[4]

    async def get_state(self, pattern: str = "rl:*") -> dict[str, Any]:
        keys = await self.redis.keys(pattern)
        now_ms = int(time.time() * 1000)
        state: dict[str, Any] = {}

        for k in keys:
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            k_type = await self.redis.type(k)
            k_type_str = k_type.decode() if isinstance(k_type, bytes) else str(k_type)
            ttl = await self.redis.ttl(k)

            if k_type_str == "string":
                val = await self.redis.get(k)
                if val is not None:
                    try:
                        tat_ms = int(val)
                        tat_rel = round((tat_ms - now_ms) / 1000.0, 3)
                        state[k_str] = {
                            "type": "string",
                            "ttl": ttl,
                            "tat_ms": tat_ms,
                            "tat_relative_seconds": tat_rel,
                        }
                    except ValueError:
                        state[k_str] = {"type": "string", "ttl": ttl, "raw": str(val)}
                else:
                    state[k_str] = {"type": "string", "ttl": ttl}
            else:
                state[k_str] = {"type": k_type_str, "ttl": ttl}

        return state

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False
