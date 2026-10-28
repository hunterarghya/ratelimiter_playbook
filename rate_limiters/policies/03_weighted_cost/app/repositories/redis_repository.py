"""Redis repository executing weighted GCRA evaluations and refunds."""

import time
from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_dir = Path(__file__).resolve().parent.parent / "lua"

        eval_path = lua_dir / "weighted_gcra.lua"
        self._eval_script = self.redis.register_script(eval_path.read_text(encoding="utf-8"))

        refund_path = lua_dir / "refund_gcra.lua"
        self._refund_script = self.redis.register_script(refund_path.read_text(encoding="utf-8"))

    async def evaluate(
        self,
        identity: str,
        limit: int,
        period: int,
        burst: int,
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int]:
        """Evaluates admission for a weighted request.

        Returns: (allowed_code, remaining, retry_after, reset, limit)
        allowed_code: 1 = allowed, 0 = rate_limited, -1 = permanently rejected (cost > burst)
        """
        key = f"rl:{{{identity}}}:weighted_gcra"
        t_ms = (period * 1000.0) / float(limit)
        tau_ms = t_ms * float(burst)

        res = await self._eval_script(
            keys=[key],
            args=[str(t_ms), str(tau_ms), str(cost), str(burst), str(now_ms)],
        )
        data = cast(list[Any], res)
        return (
            int(data[0]),
            int(data[1]),
            int(data[2]),
            int(data[3]),
            int(data[4]),
        )

    async def refund(
        self,
        identity: str,
        limit: int,
        period: int,
        burst: int,
        refund_cost: int,
        now_ms: int = 0,
    ) -> tuple[int, int, int]:
        """Refunds unused cost units into the GCRA bucket.

        Returns: (success, remaining, new_tat)
        """
        key = f"rl:{{{identity}}}:weighted_gcra"
        t_ms = (period * 1000.0) / float(limit)
        tau_ms = t_ms * float(burst)

        res = await self._refund_script(
            keys=[key],
            args=[str(t_ms), str(tau_ms), str(refund_cost), str(burst), str(now_ms)],
        )
        data = cast(list[Any], res)
        return (int(data[0]), int(data[1]), int(data[2]))

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
                        tat_rel_sec = round((tat_ms - now_ms) / 1000.0, 3)
                        state[k_str] = {
                            "type": "string",
                            "ttl": ttl,
                            "tat_ms": tat_ms,
                            "tat_relative_seconds": tat_rel_sec,
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
