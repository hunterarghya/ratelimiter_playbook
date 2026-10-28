"""Demonstration showing quota burn and race conditions in naive multi-rule check vs atomic Lua."""

import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure sub-project root is on sys.path for self-contained execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import redis.asyncio as redis  # noqa: E402
from app.repositories.redis_repository import RedisRepository  # noqa: E402
from app.schemas.rule import Rule  # noqa: E402


async def naive_client_check_and_update(
    client: redis.Redis,
    identity: str,
    rules: list[Rule],
    now_ms: int,
) -> bool:
    """Flawed naive pattern: sequentially check and update each rule one-by-one."""
    for r in rules:
        key = f"rl:{{{identity}}}:{r.name}:gcra:naive"
        t_ms = (r.period * 1000.0) / float(r.limit)
        tau_ms = t_ms * float(r.burst)

        raw_tat = await client.get(key)
        tat = int(raw_tat) if raw_tat is not None else 0
        base_tat = max(tat, now_ms)
        new_tat = int(base_tat + t_ms)
        earliest_allowed = new_tat - tau_ms

        await asyncio.sleep(0.001)

        if now_ms < earliest_allowed:
            # DENIED at this rule! But earlier rules were ALREADY charged! (Quota Burn)
            return False

        # Charge this rule immediately before checking the next rule
        await client.set(key, str(new_tat))
        await client.expire(key, 60)

    return True


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, max_connections=300)

    # Rule 1 allows 10, Rule 2 only allows 2!
    rules = [
        Rule(name="fast_rule", limit=10, period=1000, burst=10),
        Rule(name="slow_rule", limit=2, period=1000, burst=2),
    ]
    concurrency = 50
    now_ms = int(time.time() * 1000)

    print("=" * 65)
    print(" RACE & QUOTA BURN DEMO: Naive Sequential vs Atomic Multi-Rule Lua")
    print(" Policy: Rule 1 (limit 10) AND Rule 2 (limit 2)")
    print(f" Concurrency: {concurrency} parallel callers")
    print("=" * 65)

    # 1. Run Naive Client Version
    naive_id = f"demo_naive_{now_ms}"
    naive_tasks = [
        naive_client_check_and_update(client, naive_id, rules, now_ms)
        for _ in range(concurrency)
    ]
    naive_results = await asyncio.gather(*naive_tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    # Check if Rule 1 was burned
    naive_r1_key = f"rl:{{{naive_id}}}:fast_rule:gcra:naive"
    naive_r1_tat = await client.get(naive_r1_key)

    # 2. Run Atomic Lua Script Version
    lua_id = f"demo_lua_{now_ms}"
    repo = RedisRepository(client)
    lua_tasks = [
        repo.evaluate_multi_rule(lua_id, rules, now_ms=now_ms)
        for _ in range(concurrency)
    ]
    lua_results = await asyncio.gather(*lua_tasks)
    lua_allowed = sum(1 for res in lua_results if res[0] == 1)

    lua_r1_key = f"rl:{{{lua_id}}}:fast_rule:gcra"
    lua_r1_tat = await client.get(lua_r1_key)

    print(f"\n{'Engine':<30} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 75)
    naive_tag = "⛔ LEAKY / BURN" if naive_allowed > 2 else "✅ OK"
    lua_tag = "✅ EXACT" if lua_allowed == 2 else "❌ MISMATCH"
    print(f"{'Naive (Sequential Check)':<30} {2:<16} {naive_allowed:<16} {naive_tag}")
    print(f"{'Atomic Multi-Rule Lua':<30} {2:<16} {lua_allowed:<16} {lua_tag}")
    print("─" * 75)
    print("\n💡 Analysis of Quota Burn:")
    print(f"   Naive Rule 1 stored TAT: {naive_r1_tat!r} (burned quota for denied requests!)")
    print(f"   Atomic Rule 1 stored TAT: {lua_r1_tat!r} (charged strictly for 2 allowed requests!)")
    print("   The Lua script evaluates all rules before updating any state.\n")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
