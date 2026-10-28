"""Traffic generation scenarios for rate limiter demonstrations."""

import asyncio
import json
import sys
import time
from collections.abc import Callable, Coroutine
from typing import Any

import httpx


async def _send_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    req_num: int,
    start_time: float,
    identity: str = "user:alice",
    info: str = "",
) -> dict[str, Any]:
    t = round(time.time() - start_time, 2)
    req_headers = dict(headers)
    req_headers["X-User-Id"] = identity

    try:
        resp = await client.get(url, headers=req_headers)
        status = resp.status_code
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
    except Exception as exc:
        status = 0
        resp_headers = {"error": str(exc)}

    record = {
        "t": t,
        "req_num": req_num,
        "status": status,
        "headers": resp_headers,
        "identity": identity,
        "info": info,
    }
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()
    return record


async def run_steady(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    count: int = 5,
    interval: float = 0.5,
) -> None:
    start_time = time.time()
    for i in range(1, count + 1):
        await _send_request(client, url, headers, i, start_time, info="steady")
        if i < count:
            await asyncio.sleep(interval)


async def run_burst(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    burst_count: int = 6,
    wait_after: float = 0.5,
) -> None:
    start_time = time.time()
    for i in range(1, burst_count + 1):
        await _send_request(client, url, headers, i, start_time, info="burst")
        await asyncio.sleep(0.01)

    if wait_after > 0:
        await asyncio.sleep(wait_after)
        await _send_request(
            client, url, headers, burst_count + 1, start_time, info="post-wait"
        )


async def run_abuse(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    count: int = 15,
) -> None:
    start_time = time.time()
    for i in range(1, count + 1):
        await _send_request(client, url, headers, i, start_time, info="abuse")
        await asyncio.sleep(0.02)


async def run_boundary(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    limit: int = 5,
) -> None:
    """Sends a burst right before window boundary and another right after."""
    start_time = time.time()
    req_num = 1
    # First burst at end of current window
    for _ in range(limit):
        await _send_request(
            client, url, headers, req_num, start_time, info="boundary-pre"
        )
        req_num += 1
        await asyncio.sleep(0.01)

    # Wait for window boundary (short simulated pause)
    await asyncio.sleep(1.0)

    # Second burst at start of next window
    for _ in range(limit):
        await _send_request(
            client, url, headers, req_num, start_time, info="boundary-post"
        )
        req_num += 1
        await asyncio.sleep(0.01)


async def run_parallel(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    concurrency: int = 20,
) -> None:
    start_time = time.time()
    tasks = [
        _send_request(
            client, url, headers, i, start_time, info=f"parallel-{i}"
        )
        for i in range(1, concurrency + 1)
    ]
    await asyncio.gather(*tasks)


async def run_slow_clients(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    workers: int = 5,
) -> None:
    start_time = time.time()
    tasks = [
        _send_request(
            client,
            url,
            headers,
            i,
            start_time,
            info=f"worker-{i}",
        )
        for i in range(1, workers + 1)
    ]
    await asyncio.gather(*tasks)


ScenarioFunc = Callable[[httpx.AsyncClient, str, dict[str, str]], Coroutine[Any, Any, None]]

SCENARIO_MAP: dict[str, ScenarioFunc] = {
    "steady": run_steady,
    "burst": run_burst,
    "abuse": run_abuse,
    "boundary": run_boundary,
    "parallel": run_parallel,
    "slow-clients": run_slow_clients,
}

