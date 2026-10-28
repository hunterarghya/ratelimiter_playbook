"""Redis repository executing token bucket Lua script."""

from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_path = Path(__file__).resolve().parent.parent / "lua" / "token_bucket.lua"
        self._script_content = lua_path.read_text(encoding="utf-8")
        self._script = self.redis.register_script(self._script_content)

    async def evaluate_token_bucket(
        self,
        identity: str,
        rule_name: str,
        capacity: int,
        refill_rate_per_sec: float,
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        """Evaluates the token bucket rate limit atomically in Redis via Lua.

        Returns: (allowed, remaining, retry_after_seconds, reset_seconds, capacity)
        """
        key = f"rl:{{{identity}}}:{rule_name}:tb"
        res = await self._script(
            keys=[key],
            args=[
                str(capacity),
                str(refill_rate_per_sec),
                str(cost),
                str(now_ms),
            ],
        )
        data = cast(list[int], res)
        return data[0], data[1], data[2], data[3], data[4]

    async def get_state(self, pattern: str = "rl:*") -> dict[str, Any]:
        """Inspects all matching rate limiter keys in Redis."""
        keys = await self.redis.keys(pattern)
        state: dict[str, Any] = {}
        for k in keys:
            k_str = k.decode() if isinstance(k, bytes) else str(k)
            k_type = await self.redis.type(k)
            k_type_str = k_type.decode() if isinstance(k_type, bytes) else str(k_type)
            ttl = await self.redis.ttl(k)

            if k_type_str == "hash":
                raw_hash = await self.redis.hgetall(k)
                parsed_hash: dict[str, Any] = {}
                for field, val in raw_hash.items():
                    f_str = field.decode() if isinstance(field, bytes) else str(field)
                    v_str = val.decode() if isinstance(val, bytes) else str(val)
                    if f_str == "tokens":
                        try:
                            parsed_hash[f_str] = float(v_str)
                        except ValueError:
                            parsed_hash[f_str] = v_str
                    elif f_str == "last_ts":
                        try:
                            parsed_hash[f_str] = int(v_str)
                        except ValueError:
                            parsed_hash[f_str] = v_str
                    else:
                        parsed_hash[f_str] = v_str

                state[k_str] = {
                    "type": "hash",
                    "ttl": ttl,
                    "fields": parsed_hash,
                }
            else:
                state[k_str] = {
                    "type": k_type_str,
                    "ttl": ttl,
                }
        return state

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except Exception:
            return False
