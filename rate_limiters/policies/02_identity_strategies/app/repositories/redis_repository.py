"""Redis repository executing multi-identity GCRA Lua evaluations."""

import time
from pathlib import Path
from typing import Any, cast

import redis.asyncio as aioredis

from app.schemas.rule import Rule


class RedisRepository:
    def __init__(self, client: aioredis.Redis) -> None:
        self.redis = client
        lua_path = Path(__file__).resolve().parent.parent / "lua" / "identity_gcra.lua"
        self._script_content = lua_path.read_text(encoding="utf-8")
        self._script = self.redis.register_script(self._script_content)

    async def evaluate_rules(
        self,
        targets: list[tuple[str, Rule]],
        cost: int = 1,
        now_ms: int = 0,
    ) -> tuple[int, int, int, int, int, str]:
        """Atomically evaluates rate limit rules across one or more identity keys.

        Returns: (allowed, remaining, retry_after, reset, limit, violated_rule)
        """
        keys = [f"rl:{{{identity}}}:{rule.name}:gcra" for identity, rule in targets]
        args: list[str] = [str(cost), str(now_ms)]

        for identity, rule in targets:
            t_ms = (rule.period * 1000.0) / float(rule.limit)
            tau_ms = t_ms * float(rule.burst)
            rule_label = f"{identity}:{rule.name}"
            args.extend([str(t_ms), str(tau_ms), str(rule.burst), rule_label])

        res = await self._script(keys=keys, args=args)
        data = cast(list[Any], res)

        allowed = int(data[0])
        remaining = int(data[1])
        retry_after = int(data[2])
        reset = int(data[3])
        limit = int(data[4])
        violated_raw = data[5]
        if isinstance(violated_raw, bytes):
            violated_rule = violated_raw.decode()
        else:
            violated_rule = str(violated_raw)

        return allowed, remaining, retry_after, reset, limit, violated_rule

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
