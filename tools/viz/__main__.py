"""Live terminal timeline renderer for rate limiter traffic."""

import argparse
import json
import sys
from typing import Any


def format_row(record: dict[str, Any]) -> tuple[str, bool]:
    t = float(record.get("t", 0.0))
    req_num = record.get("req_num", 1)
    status = record.get("status", 200)
    headers = record.get("headers", {})

    is_allowed = status < 400
    if is_allowed:
        result_str = f"✅ {status}"
    else:
        result_str = f"⛔ {status}"

    remaining = headers.get("ratelimit-remaining", "-")
    retry_after = headers.get("retry-after", "-")
    if not retry_after or retry_after == "0":
        retry_after = "-"

    # Extract redis state from header or direct field
    redis_state = (
        record.get("redis_state")
        or record.get("limiter_state")
        or headers.get("x-redis-state")
        or "-"
    )

    row = (
        f" {t:>5.2f}   #{req_num:<6}  {result_str:<8}  "
        f"{str(remaining):<10}  {str(retry_after):<12}  {redis_state}"
    )
    return row, is_allowed


def render(lines: list[str]) -> None:
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        print("No valid traffic records to display.")
        return

    first = records[0]
    headers_0 = first.get("headers", {})
    algorithm = first.get("algorithm") or "GCRA"
    limit = first.get("limit") or headers_0.get("ratelimit-limit") or "2/s"
    if "/" not in str(limit):
        limit = f"{limit}/s"
    burst = first.get("burst") or 4
    identity = first.get("identity") or "user:alice"

    print(f"{algorithm} · limit {limit} · burst {burst} · identity {identity}")
    print("─" * 61)
    print(" t(s)   request   result    remaining   retry_after   redis state")

    allowed_count = 0
    denied_count = 0
    consecutive_burst = 0
    peak_burst = 0

    for rec in records:
        row, is_allowed = format_row(rec)
        print(row)
        if is_allowed:
            allowed_count += 1
            consecutive_burst += 1
            if consecutive_burst > peak_burst:
                peak_burst = consecutive_burst
        else:
            denied_count += 1
            consecutive_burst = 0

    print("─" * 61)
    print(
        f" allowed {allowed_count} · denied {denied_count} · peak burst {peak_burst}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Rate limiter timeline visualizer")
    parser.add_argument("--file", default=None, help="Read JSON lines from file instead of stdin")
    args = parser.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    render(lines)


if __name__ == "__main__":
    main()
