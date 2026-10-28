"""Demonstration showing the race condition in naive client-side logic vs atomic Lua script."""

import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure sub-project root is on sys.path for self-contained app import
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import redis.asyncio as redis  # noqa: E402
from app.repositories.redis_repository import RedisRepository  # noqa: E402
from app.schemas.rule import Rule  # noqa: E402
from app.services.rate_limiter_service import RateLimiterService  # noqa: E402


async def naive_client_check(client: redis.Redis, key: str, limit: int, window: int) -> bool:
    """FLAWED implementation: reads count from Redis, pauses, then writes.

    Simulates the network round-trip delay between application instances.
    """
    now = time.time()
    clear_before = now - window
    await client.zremrangebyscore(key, "-inf", clear_before)

    # 1. READ
    count = await client.zcard(key)

    # Simulated network round-trip / processing gap
    await asyncio.sleep(0.002)

    # 2. DECIDE & WRITE
    if count < limit:
        await client.zadd(key, {f"{now}:{time.time_ns()}": now})
        return True
    return False


async def run_race_demo() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client = redis.from_url(redis_url, max_connections=300, decode_responses=True)
    limit = 10
    window = 60
    concurrent_requests = 200

    print("=================================================================")
    print(" RACE CONDITION DEMO: Naive Client Check vs Atomic Lua Script")
    print(
        f" Limit: {limit} requests / {window}s window · "
        f"Concurrency: {concurrent_requests} parallel callers"
    )
    print("=================================================================\n")

    # 1. Test Naive Client
    naive_key = f"rl:{{demo:naive}}:{int(time.time()*1000)}"
    await client.delete(naive_key)

    tasks_naive = [
        naive_client_check(client, naive_key, limit, window)
        for _ in range(concurrent_requests)
    ]
    naive_results = await asyncio.gather(*tasks_naive)
    naive_allowed = sum(1 for r in naive_results if r is True)
    await client.delete(naive_key)

    # 2. Test Atomic Lua
    repo = RedisRepository(client)
    service = RateLimiterService(repo)
    rule = Rule(name="race", limit=limit, period=window)
    lua_identity = f"demo:lua_{int(time.time()*1000)}"
    lua_key = service.build_key(lua_identity, rule.name)
    await client.delete(lua_key)

    tasks_lua = [
        service.evaluate(lua_identity, rule)
        for _ in range(concurrent_requests)
    ]
    lua_decisions = await asyncio.gather(*tasks_lua)
    lua_allowed = sum(1 for d in lua_decisions if d.allowed is True)
    await client.delete(lua_key)

    naive_status = "⛔ LEAKY (RACE)" if naive_allowed > limit else "OK"
    lua_status = "✅ EXACT" if lua_allowed == limit else "FAILED"

    # Report results
    print(f"{'Engine':<25} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 70)
    print(f"{'Naive Client (Read-Then-Write)':<25} {limit:<16} {naive_allowed:<16} {naive_status}")
    print(f"{'Atomic Lua (EVALSHA)':<25} {limit:<16} {lua_allowed:<16} {lua_status}")
    print("─" * 70)

    if naive_allowed > limit:
        print(
            f"\n💡 Notice: The naive client let {naive_allowed} requests through (limit {limit})!"
        )
        print("   Between the read (ZCARD) and write (ZADD), other instances slipped in.")
        print("   The Lua script runs atomically inside Redis, allowing EXACTLY 10 requests.")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(run_race_demo())
