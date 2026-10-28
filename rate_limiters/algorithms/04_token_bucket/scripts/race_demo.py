"""Demonstration showing the race condition in naive client-side logic vs atomic Lua script."""

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


async def naive_client_check_and_consume(
    client: redis.Redis,
    identity: str,
    rule_name: str,
    capacity: int,
    refill_rate: float,
    now_ms: int,
) -> bool:
    """Flawed naive pattern: read hash fields, compute refill in Python, then write back."""
    key = f"rl:{{{identity}}}:{rule_name}:tb:naive"

    # Step 1: Read hash fields (GET)
    raw_data = await client.hmget(key, ["tokens", "last_ts"])  # type: ignore[arg-type]
    raw_tokens, raw_last_ts = raw_data[0], raw_data[1]

    if raw_tokens is None or raw_last_ts is None:
        tokens = float(capacity)
        last_ts = now_ms
    else:
        last_ts = int(raw_last_ts)
        elapsed_sec = max(0.0, (now_ms - last_ts) / 1000.0)
        tokens = min(float(capacity), float(raw_tokens) + elapsed_sec * refill_rate)

    # Context switch / network latency window where concurrent requests slip in!
    await asyncio.sleep(0.001)

    # Step 2: Check and write back (SET)
    if tokens >= 1.0:
        new_tokens = tokens - 1.0
        await client.hset(key, mapping={"tokens": str(new_tokens), "last_ts": str(now_ms)})
        await client.expire(key, 60)
        return True
    return False


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, max_connections=300)

    capacity = 10
    refill_rate = 0.0001  # negligible refill during demonstration
    concurrency = 200
    now_ms = int(time.time() * 1000)

    print("=" * 65)
    print(" RACE CONDITION DEMO: Naive Client Check vs Atomic Lua Script")
    print(" Algorithm: Token Bucket (burst capacity + lazy refill)")
    print(f" Limit: {capacity} burst capacity · Concurrency: {concurrency} parallel callers")
    print("=" * 65)

    # 1. Run Naive Client Version
    naive_id = f"demo_naive_{now_ms}"
    await client.delete(f"rl:{{{naive_id}}}:race:tb:naive")

    naive_tasks = [
        naive_client_check_and_consume(client, naive_id, "race", capacity, refill_rate, now_ms)
        for _ in range(concurrency)
    ]
    naive_results = await asyncio.gather(*naive_tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    # 2. Run Atomic Lua Script Version
    lua_id = f"demo_lua_{now_ms}"
    repo = RedisRepository(client)
    await client.delete(f"rl:{{{lua_id}}}:race:tb")

    lua_tasks = [
        repo.evaluate_token_bucket(lua_id, "race", capacity, refill_rate, cost=1)
        for _ in range(concurrency)
    ]
    lua_results = await asyncio.gather(*lua_tasks)
    lua_allowed = sum(1 for res in lua_results if res[0] == 1)

    print(f"\n{'Engine':<30} {'Intended Limit':<16} {'Actual Allowed':<16} {'Result'}")
    print("─" * 75)
    naive_tag = "⛔ LEAKY (RACE)" if naive_allowed > capacity else "✅ OK"
    lua_tag = "✅ EXACT" if lua_allowed == capacity else "❌ MISMATCH"
    print(f"{'Naive Client (Read-Then-Write)':<30} {capacity:<16} {naive_allowed:<16} {naive_tag}")
    print(f"{'Atomic Lua (HMGET + HSET)':<30} {capacity:<16} {lua_allowed:<16} {lua_tag}")
    print("─" * 75)
    print(f"\n💡 Notice: The naive client let {naive_allowed} requests through (limit {capacity})!")
    print("   Multiple coroutines read the same token balance before any could update it.")
    print("   The Lua script evaluates and consumes tokens inside Redis in a single atomic step.\n")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
