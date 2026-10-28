"""Demonstration showing the race condition in naive client-side check vs atomic Lua script."""

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


async def naive_client_acquire(
    client: redis.Redis,
    identity: str,
    rule_name: str,
    limit: int,
    lease_id: str,
    lease_ttl_ms: int,
    now_ms: int,
) -> bool:
    """Flawed naive pattern: read ZCARD in Python, then ZADD."""
    key = f"rl:{{{identity}}}:{rule_name}:leases:naive"

    # Step 1: Read active count (ZCARD)
    active = await client.zcard(key)

    # Context switch / network latency window where concurrent callers slip in!
    await asyncio.sleep(0.001)

    # Step 2: Check and write back (ZADD)
    if active < limit:
        exp_ms = now_ms + lease_ttl_ms
        await client.zadd(key, {lease_id: exp_ms})
        await client.expire(key, 60)
        return True
    return False


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, max_connections=300)

    limit = 10
    lease_ttl_ms = 60_000
    concurrency = 200
    now_ms = int(time.time() * 1000)

    print("=" * 65)
    print(" RACE CONDITION DEMO: Naive Client Check vs Atomic Lua Script")
    print(" Algorithm: Concurrency Limiter (in-flight lease management)")
    print(f" Limit: {limit} concurrent slots · Concurrency: {concurrency} parallel callers")
    print("=" * 65)

    # 1. Run Naive Client Version
    naive_id = f"demo_naive_{now_ms}"
    await client.delete(f"rl:{{{naive_id}}}:race:leases:naive")

    naive_tasks = [
        naive_client_acquire(
            client, naive_id, "race", limit, f"naive-{i}", lease_ttl_ms, now_ms
        )
        for i in range(concurrency)
    ]
    naive_results = await asyncio.gather(*naive_tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    # 2. Run Atomic Lua Script Version
    lua_id = f"demo_lua_{now_ms}"
    repo = RedisRepository(client)
    await client.delete(f"rl:{{{lua_id}}}:race:leases")

    lua_tasks = [
        repo.acquire_lease(
            lua_id, "race", limit, f"lua-{i}", lease_ttl_ms, now_ms
        )
        for i in range(concurrency)
    ]
    lua_results = await asyncio.gather(*lua_tasks)
    lua_allowed = sum(1 for res in lua_results if res[0] == 1)

    print(f"\n{'Engine':<30} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 75)
    naive_tag = "⛔ LEAKY (RACE)" if naive_allowed > limit else "✅ OK"
    lua_tag = "✅ EXACT" if lua_allowed == limit else "❌ MISMATCH"
    print(f"{'Naive Client (ZCARD then ZADD)':<30} {limit:<16} {naive_allowed:<16} {naive_tag}")
    print(f"{'Atomic Lua (Clean + Count + ZADD)':<30} {limit:<16} {lua_allowed:<16} {lua_tag}")
    print("─" * 75)
    print(f"\n💡 Notice: The naive client let {naive_allowed} leases through (limit {limit})!")
    print("   Multiple coroutines read ZCARD=0 before any could call ZADD.")
    print("   The Lua script cleans expired, counts, and adds in one atomic Redis step.\n")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
