"""CLI to inspect rl:* rate limiter keys in Redis."""

import argparse
import os
import time
from typing import Any, cast

import redis


def inspect_redis(redis_url: str, pattern: str = "rl:*") -> None:
    r: redis.Redis = redis.from_url(redis_url, decode_responses=True)
    try:
        raw_keys = r.keys(pattern)
        keys = sorted(str(k) for k in raw_keys)
    except Exception as exc:
        print(f"Error connecting to Redis at {redis_url}: {exc}")
        return

    if not keys:
        print(f"No keys matching pattern '{pattern}' found in Redis ({redis_url}).")
        return

    now_ms = time.time() * 1000.0

    print(f"\nFound {len(keys)} key(s) matching '{pattern}':\n")
    print(f"{'KEY':<45} {'TYPE':<8} {'TTL':<10} {'VALUE / STRUCTURE'}")
    print("─" * 90)

    for key in keys:
        raw_type = r.type(key)
        key_type = str(raw_type)
        ttl = int(r.ttl(key))
        ttl_str = f"{ttl}s" if ttl >= 0 else ("no ttl" if ttl == -1 else "expired")

        if key_type == "string":
            raw_val = r.get(key)
            val_display = str(raw_val) if raw_val is not None else "None"
            # Check if this could be a GCRA TAT timestamp (milliseconds)
            if raw_val is not None:
                try:
                    tat_num = float(str(raw_val))
                    if tat_num > 1e11:  # epoch ms timestamp
                        diff_s = (tat_num - now_ms) / 1000.0
                        if diff_s > 0:
                            val_display += f"  (TAT = +{diff_s:.2f}s)"
                        else:
                            val_display += f"  (TAT expired {-diff_s:.2f}s ago)"
                except (ValueError, TypeError):
                    pass

        elif key_type == "hash":
            hdata = cast(dict[str, Any], r.hgetall(key))
            formatted = ", ".join(f"{str(k)}: {str(v)}" for k, v in hdata.items())
            val_display = f"{{{formatted}}}"

        elif key_type == "zset":
            zdata = cast(list[tuple[Any, float]], r.zrange(key, 0, -1, withscores=True))
            formatted = ", ".join(f"{str(m)} (score={score:g})" for m, score in zdata)
            val_display = f"[{formatted}]"

        elif key_type == "set":
            sdata = cast(set[Any], r.smembers(key))
            val_display = f"{{{', '.join(str(m) for m in sdata)}}}"

        else:
            val_display = f"unsupported type: {key_type}"

        print(f"{key:<45} {key_type:<8} {ttl_str:<10} {val_display}")

    print("─" * 90)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect rate limiter keys in Redis")
    default_url = os.environ.get("REDIS_URL")
    if not default_url:
        is_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "1"
        default_url = "redis://redis:6379/0" if is_docker else "redis://localhost:6379/0"

    parser.add_argument(
        "--redis-url", default=default_url, help=f"Redis URL (default: {default_url})"
    )
    parser.add_argument("--pattern", default="rl:*", help="Key pattern to inspect (default: rl:*)")
    args = parser.parse_args()

    inspect_redis(args.redis_url, args.pattern)


if __name__ == "__main__":
    main()
