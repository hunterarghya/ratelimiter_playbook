"""Demonstration showing race conditions in naive check-and-set vs atomic Weighted GCRA Lua."""

import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import redis.asyncio as redis  # noqa: E402
from app.repositories.redis_repository import RedisRepository  # noqa: E402


async def naive_weighted_check(
    client: redis.Redis,
    identity: str,
    cost: int,
    limit: int,
    burst: int,
    period: int,
    now_ms: int,
) -> bool:
    """Naive non-atomic check: read TAT, calculate, sleep (simulating I/O), write."""
    key = f"rl:{{{identity}}}:weighted_gcra:naive"
    t_ms = (period * 1000.0) / float(limit)
    tau_ms = t_ms * float(burst)

    raw_tat = await client.get(key)
    tat = int(raw_tat) if raw_tat is not None else 0
    base_tat = max(tat, now_ms)
    new_tat = int(base_tat + (t_ms * cost))
    earliest_allowed = new_tat - tau_ms

    await asyncio.sleep(0.001)

    if now_ms < earliest_allowed:
        return False

    await client.set(key, str(new_tat))
    await client.expire(key, 60)
    return True


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, max_connections=300)

    limit = 20
    burst = 20
    period = 1000
    cost = 5  # Each caller takes 5 units -> only 4 can fit in burst of 20
    concurrency = 40
    now_ms = int(time.time() * 1000)

    print("=" * 68)
    print(" RACE DEMO: Naive Check-and-Set vs Atomic Weighted GCRA Lua")
    print(f" Burst Capacity: {burst} units | Cost per call: {cost} units")
    print(f" Allowed target: {burst // cost} calls | Concurrency: {concurrency} callers")
    print("=" * 68)

    # 1. Naive Client Check
    naive_id = f"demo_naive_{now_ms}"
    naive_tasks = [
        naive_weighted_check(client, naive_id, cost, limit, burst, period, now_ms)
        for _ in range(concurrency)
    ]
    naive_results = await asyncio.gather(*naive_tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    # 2. Atomic Weighted GCRA Lua
    lua_id = f"demo_lua_{now_ms}"
    repo = RedisRepository(client)
    lua_tasks = [
        repo.evaluate(lua_id, limit, period, burst, cost=cost, now_ms=now_ms)
        for _ in range(concurrency)
    ]
    lua_results = await asyncio.gather(*lua_tasks)
    lua_allowed = sum(1 for res in lua_results if res[0] == 1)

    print(f"\n{'Engine':<28} {'Burst':<8} {'Cost/Req':<10} {'Allowed':<10} {'Result'}")
    print("─" * 68)
    naive_tag = "⛔ OVER-ADMITTED" if naive_allowed > 4 else "✅ OK"
    lua_tag = "✅ EXACT" if lua_allowed == 4 else "❌ MISMATCH"
    print(f"{'Naive (Sequential)':<28} {burst:<8} {cost:<10} {naive_allowed:<10} {naive_tag}")
    print(f"{'Atomic Weighted Lua':<28} {burst:<8} {cost:<10} {lua_allowed:<10} {lua_tag}")
    print("─" * 68)
    print("\n💡 Key Insight:")
    print("   Under concurrent load, naive check-and-set allows multiple callers to read")
    print("   the same stale TAT, granting far more capacity than the burst budget allows.")
    print("   Weighted GCRA Lua serializes evaluation and TAT advancement atomically.\n")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
