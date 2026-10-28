"""Demonstration showing the race condition in naive client-side logic vs atomic Lua script."""

import asyncio
import math
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


async def naive_client_check(
    client: redis.Redis, curr_key: str, prev_key: str,
    limit: int, window_ms: int, now_ms: int, window_start_ms: int,
) -> bool:
    """FLAWED implementation: reads counters from Redis, pauses, then writes.

    Simulates the network round-trip delay between application instances.
    """
    # 1. READ both counters
    raw_prev = await client.get(prev_key)
    raw_curr = await client.get(curr_key)
    prev_count = int(raw_prev) if raw_prev else 0
    curr_count = int(raw_curr) if raw_curr else 0

    # Simulated network round-trip / processing gap
    await asyncio.sleep(0.002)

    # 2. COMPUTE the weighted estimate
    elapsed_ms = now_ms - window_start_ms
    elapsed_fraction = elapsed_ms / window_ms if window_ms > 0 else 0
    weight = 1 - elapsed_fraction
    estimated = math.floor(prev_count * weight + curr_count)

    # 3. DECIDE & WRITE
    if estimated < limit:
        await client.incr(curr_key)
        await client.pexpire(curr_key, window_ms * 2)
        return True
    return False


async def run_race_demo() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client = redis.from_url(redis_url, max_connections=300, decode_responses=True)
    limit = 10
    window = 60
    window_ms = window * 1000
    concurrent_requests = 200

    print("=================================================================")
    print(" RACE CONDITION DEMO: Naive Client Check vs Atomic Lua Script")
    print(" Algorithm: Sliding Window Counter (two-counter approximation)")
    print(
        f" Limit: {limit} requests / {window}s window · "
        f"Concurrency: {concurrent_requests} parallel callers"
    )
    print("=================================================================\n")

    # Fixed timestamp for all requests
    fixed_now_ms = 75000  # 15s into window #1 (60s windows)
    window_num = fixed_now_ms // window_ms
    window_start_ms = window_num * window_ms

    # 1. Test Naive Client
    naive_curr_key = f"rl:{{demo:naive_counter}}:{int(time.time()*1000)}:swc:{window_num}"
    naive_prev_key = f"rl:{{demo:naive_counter}}:{int(time.time()*1000)}:swc:{window_num - 1}"
    await client.delete(naive_curr_key, naive_prev_key)

    tasks_naive = [
        naive_client_check(
            client, naive_curr_key, naive_prev_key,
            limit, window_ms, fixed_now_ms, window_start_ms,
        )
        for _ in range(concurrent_requests)
    ]
    naive_results = await asyncio.gather(*tasks_naive)
    naive_allowed = sum(1 for r in naive_results if r is True)
    await client.delete(naive_curr_key, naive_prev_key)

    # 2. Test Atomic Lua
    repo = RedisRepository(client)
    service = RateLimiterService(repo)
    rule = Rule(name="race", limit=limit, period=window)
    lua_identity = f"demo:lua_counter_{int(time.time()*1000)}"

    tasks_lua = [
        service.evaluate(lua_identity, rule, current_time=fixed_now_ms / 1000.0)
        for _ in range(concurrent_requests)
    ]
    lua_decisions = await asyncio.gather(*tasks_lua)
    lua_allowed = sum(1 for d in lua_decisions if d.allowed is True)

    # Clean up
    keys_to_del = await client.keys(f"rl:{{{lua_identity}}}:*")
    if keys_to_del:
        await client.delete(*keys_to_del)

    naive_status = "⛔ LEAKY (RACE)" if naive_allowed > limit else "OK"
    lua_status = "✅ EXACT" if lua_allowed == limit else "FAILED"

    # Report results
    print(f"{'Engine':<30} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 75)
    print(
        f"{'Naive Client (Read-Then-Write)':<30} {limit:<16} {naive_allowed:<16} {naive_status}"
    )
    print(f"{'Atomic Lua (EVALSHA)':<30} {limit:<16} {lua_allowed:<16} {lua_status}")
    print("─" * 75)

    if naive_allowed > limit:
        print(
            f"\n💡 Notice: The naive client let {naive_allowed} requests through (limit {limit})!"
        )
        print("   Between the GET (read counters) and INCR (write), other instances slipped in.")
        print("   The Lua script reads, computes, and conditionally increments atomically.")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(run_race_demo())
