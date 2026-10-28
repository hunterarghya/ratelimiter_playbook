"""Demonstration showing the race condition in naive client-side GCRA vs atomic Lua script."""

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


async def naive_client_check_and_update(
    client: redis.Redis,
    identity: str,
    rule_name: str,
    t_ms: float,
    tau_ms: float,
    now_ms: int,
) -> bool:
    """Flawed naive pattern: read TAT string, compute in Python, then write back."""
    key = f"rl:{{{identity}}}:{rule_name}:gcra:naive"

    # Step 1: Read TAT from Redis (GET)
    raw_tat = await client.get(key)
    tat = int(raw_tat) if raw_tat is not None else 0

    base_tat = max(tat, now_ms)
    new_tat = int(base_tat + t_ms)
    earliest_allowed = new_tat - tau_ms

    # Context switch / network latency window where concurrent requests slip in!
    await asyncio.sleep(0.001)

    # Step 2: Check and write back (SET)
    if now_ms >= earliest_allowed:
        await client.set(key, str(new_tat))
        await client.expire(key, 60)
        return True
    return False


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, max_connections=300)

    burst = 10
    t_ms = 10_000_000.0  # negligible recovery during test
    tau_ms = t_ms * burst
    concurrency = 200
    now_ms = int(time.time() * 1000)

    print("=" * 65)
    print(" RACE CONDITION DEMO: Naive Client Check vs Atomic Lua Script")
    print(" Algorithm: GCRA (Generic Cell Rate Algorithm / TAT)")
    print(f" Limit: {burst} burst capacity · Concurrency: {concurrency} parallel callers")
    print("=" * 65)

    # 1. Run Naive Client Version
    naive_id = f"demo_naive_{now_ms}"
    await client.delete(f"rl:{{{naive_id}}}:race:gcra:naive")

    naive_tasks = [
        naive_client_check_and_update(client, naive_id, "race", t_ms, tau_ms, now_ms)
        for _ in range(concurrency)
    ]
    naive_results = await asyncio.gather(*naive_tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    # 2. Run Atomic Lua Script Version
    lua_id = f"demo_lua_{now_ms}"
    repo = RedisRepository(client)
    await client.delete(f"rl:{{{lua_id}}}:race:gcra")

    lua_tasks = [
        repo.evaluate_gcra(lua_id, "race", t_ms, tau_ms, burst, cost=1)
        for _ in range(concurrency)
    ]
    lua_results = await asyncio.gather(*lua_tasks)
    lua_allowed = sum(1 for res in lua_results if res[0] == 1)

    print(f"\n{'Engine':<30} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 75)
    naive_tag = "⛔ LEAKY (RACE)" if naive_allowed > burst else "✅ OK"
    lua_tag = "✅ EXACT" if lua_allowed == burst else "❌ MISMATCH"
    print(f"{'Naive Client (Read-Then-Write)':<30} {burst:<16} {naive_allowed:<16} {naive_tag}")
    print(f"{'Atomic Lua (GET + SET)':<30} {burst:<16} {lua_allowed:<16} {lua_tag}")
    print("─" * 75)
    print(f"\n💡 Notice: The naive client let {naive_allowed} requests through (limit {burst})!")
    print("   Multiple coroutines read the un-incremented TAT concurrently.")
    print("   The Lua script reads, checks, and updates TAT inside Redis atomically.\n")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
