"""Demonstration showing race conditions in naive check-and-set vs atomic GCRA Lua."""

import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import redis.asyncio as redis  # noqa: E402
from app.repositories.redis_repository import RedisRepository  # noqa: E402


async def naive_check(
    client: redis.Redis,
    identity: str,
    t_ms: float,
    tau_ms: float,
    now_ms: int,
) -> bool:
    key = f"rl:{{{identity}}}:naive_check"
    raw_tat = await client.get(key)
    tat = int(raw_tat) if raw_tat is not None else 0
    base_tat = max(tat, now_ms)
    new_tat = int(base_tat + t_ms)
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

    limit = 5
    burst = 5
    period = 10.0
    t_ms = (period * 1000.0) / float(limit)
    tau_ms = t_ms * float(burst)
    concurrency = 30
    now_ms = int(time.time() * 1000)

    print("=" * 68)
    print(" RACE DEMO: Naive Check-and-Set vs Atomic GCRA Lua")
    print(f" Burst Capacity: {burst} | Concurrency: {concurrency} callers")
    print("=" * 68)

    # 1. Naive Check-and-Set
    naive_id = f"naive_race_{now_ms}"
    tasks = [naive_check(client, naive_id, t_ms, tau_ms, now_ms) for _ in range(concurrency)]
    naive_results = await asyncio.gather(*tasks)
    naive_allowed = sum(1 for r in naive_results if r)

    print("\n[1] Naive Check-and-Set (Read-Modify-Write):")
    print(f"    Allowed: {naive_allowed} / {concurrency} requests (Expected: <= {burst})")
    if naive_allowed > burst:
        over = naive_allowed - burst
        print(f"    --> BUG OBSERVED: Over-admitted by {over} requests due to race condition!")
    else:
        print("    --> No race detected in this run.")

    # 2. Atomic GCRA Lua script
    repo = RedisRepository(client)
    atomic_id = f"atomic_race_{now_ms}"

    async def atomic_call() -> int:
        allowed, _, _, _, _ = await repo.evaluate(
            identity=atomic_id,
            rule_name="std",
            t_ms=t_ms,
            tau_ms=tau_ms,
            burst=burst,
            cost=1,
            now_ms=now_ms,
        )
        return allowed

    atomic_tasks = [atomic_call() for _ in range(concurrency)]
    atomic_results = await asyncio.gather(*atomic_tasks)
    atomic_allowed = sum(1 for r in atomic_results if r == 1)

    print("\n[2] Atomic GCRA Lua Script:")
    print(f"    Allowed: {atomic_allowed} / {concurrency} requests (Expected: exactly {burst})")
    if atomic_allowed == burst:
        print("    --> PASS: Exactly atomic admission, zero race conditions!")
    else:
        print(f"    --> UNEXPECTED: Allowed {atomic_allowed} != {burst}")

    print("=" * 68)
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
