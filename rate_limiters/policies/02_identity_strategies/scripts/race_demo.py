"""Demonstration showing race conditions and quota burn across identities vs atomic Lua."""

import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import redis.asyncio as redis  # noqa: E402
from app.repositories.redis_repository import RedisRepository  # noqa: E402
from app.schemas.rule import Rule  # noqa: E402


async def naive_multi_identity_check(
    client: redis.Redis,
    targets: list[tuple[str, Rule]],
    now_ms: int,
) -> bool:
    """Naive client evaluation: sequential check-and-set across identity keys."""
    for identity, rule in targets:
        key = f"rl:{{{identity}}}:{rule.name}:gcra:naive"
        t_ms = (rule.period * 1000.0) / float(rule.limit)
        tau_ms = t_ms * float(rule.burst)

        raw_tat = await client.get(key)
        tat = int(raw_tat) if raw_tat is not None else 0
        base_tat = max(tat, now_ms)
        new_tat = int(base_tat + t_ms)
        earliest_allowed = new_tat - tau_ms

        await asyncio.sleep(0.001)

        if now_ms < earliest_allowed:
            # Denied on this identity! But prior identities were already charged!
            return False

        await client.set(key, str(new_tat))
        await client.expire(key, 60)

    return True


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, max_connections=300)

    # IP allows 20, User allows 2
    ip_rule = Rule(name="ip_tier", limit=20, period=1000, burst=20)
    user_rule = Rule(name="user_tier", limit=2, period=1000, burst=2)

    concurrency = 40
    now_ms = int(time.time() * 1000)

    print("=" * 68)
    print(" RACE & QUOTA BURN DEMO: Naive Multi-Identity vs Atomic Lua")
    print(" Target: IP (limit 20) AND User (limit 2)")
    print(f" Concurrency: {concurrency} parallel requests")
    print("=" * 68)

    # 1. Naive Client Check
    naive_ip = f"naive_ip_{now_ms}"
    naive_user = f"naive_user_{now_ms}"
    naive_targets = [(naive_ip, ip_rule), (naive_user, user_rule)]

    naive_tasks = [
        naive_multi_identity_check(client, naive_targets, now_ms)
        for _ in range(concurrency)
    ]
    naive_results = await asyncio.gather(*naive_tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    naive_ip_tat = await client.get(f"rl:{{{naive_ip}}}:ip_tier:gcra:naive")

    # 2. Atomic Lua Evaluation
    lua_ip = f"lua_ip_{now_ms}"
    lua_user = f"lua_user_{now_ms}"
    lua_targets = [(lua_ip, ip_rule), (lua_user, user_rule)]

    repo = RedisRepository(client)
    lua_tasks = [
        repo.evaluate_rules(lua_targets, now_ms=now_ms)
        for _ in range(concurrency)
    ]
    lua_results = await asyncio.gather(*lua_tasks)
    lua_allowed = sum(1 for res in lua_results if res[0] == 1)

    lua_ip_tat = await client.get(f"rl:{{{lua_ip}}}:ip_tier:gcra")

    print(f"\n{'Engine':<30} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 75)
    naive_tag = "⛔ LEAKY / BURN" if naive_allowed > 2 else "✅ OK"
    lua_tag = "✅ EXACT" if lua_allowed == 2 else "❌ MISMATCH"
    print(f"{'Naive (Sequential)':<30} {2:<16} {naive_allowed:<16} {naive_tag}")
    print(f"{'Atomic Multi-Identity Lua':<30} {2:<16} {lua_allowed:<16} {lua_tag}")
    print("─" * 75)
    print("\n💡 Analysis:")
    print(f"   Naive IP stored TAT: {naive_ip_tat!r} (burned quota on rejected user requests!)")
    print(f"   Atomic IP stored TAT: {lua_ip_tat!r} (charged strictly for the 2 allowed requests!)")
    print("   Atomic Lua ensures neither identity burns quota unless both are admitted.\n")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
