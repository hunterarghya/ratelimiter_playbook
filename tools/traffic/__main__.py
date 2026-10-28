"""CLI for the traffic generator."""

import argparse
import asyncio
import os
import sys

import httpx

from tools.traffic.scenarios import SCENARIO_MAP, ScenarioFunc

PROJECT_PORTS = {
    "fixed-window": 8101,
    "01_fixed_window": 8101,
    "sliding-log": 8102,
    "02_sliding_window_log": 8102,
    "sliding-counter": 8103,
    "03_sliding_window_counter": 8103,
    "token-bucket": 8104,
    "04_token_bucket": 8104,
    "gcra": 8105,
    "05_gcra": 8105,
    "concurrency": 8106,
    "06_concurrency": 8106,
    "multi-rule": 8201,
    "01_multi_rule": 8201,
    "identity": 8202,
    "02_identity_strategies": 8202,
    "weighted-cost": 8203,
    "03_weighted_cost": 8203,
    "failure-modes": 8204,
    "04_failure_modes": 8204,
    "shadow-mode": 8205,
    "05_shadow_mode": 8205,
}

PROJECT_CONTAINER_HOSTS = {
    "fixed-window": "fixed-window",
    "01_fixed_window": "fixed-window",
    "sliding-log": "sliding-log",
    "02_sliding_window_log": "sliding-log",
    "sliding-counter": "sliding-counter",
    "03_sliding_window_counter": "sliding-counter",
    "token-bucket": "token-bucket",
    "04_token_bucket": "token-bucket",
    "gcra": "gcra",
    "05_gcra": "gcra",
    "concurrency": "concurrency",
    "06_concurrency": "concurrency",
    "multi-rule": "multi-rule",
    "01_multi_rule": "multi-rule",
    "identity": "identity",
    "02_identity_strategies": "identity",
    "weighted-cost": "weighted-cost",
    "03_weighted_cost": "weighted-cost",
    "failure-modes": "failure-modes",
    "04_failure_modes": "failure-modes",
    "shadow-mode": "shadow-mode",
    "05_shadow_mode": "shadow-mode",
}


def resolve_base_url(project: str | None, custom_url: str | None) -> str:
    if custom_url:
        return custom_url.rstrip("/")

    if not project:
        return "http://localhost:8105"

    port = PROJECT_PORTS.get(project, 8000)
    service_host = PROJECT_CONTAINER_HOSTS.get(project, project)

    # Check if we are running inside Docker network
    # In docker, the service name is resolvable directly on port 8000
    is_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "1"
    if is_docker:
        return f"http://{service_host}:8000"

    return f"http://localhost:{port}"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rate limiter traffic generator")
    parser.add_argument("--project", default="gcra", help="Target project profile (e.g. gcra)")
    parser.add_argument("--url", default=None, help="Explicit target URL")
    parser.add_argument(
        "--endpoint", default="/demo/limited", help="Endpoint path (default: /demo/limited)"
    )
    parser.add_argument(
        "--scenario",
        default="burst",
        choices=list(SCENARIO_MAP.keys()) + ["all"],
        help="Traffic scenario to run",
    )
    args = parser.parse_args()

    base_url = resolve_base_url(args.project, args.url)
    target_url = f"{base_url}{args.endpoint}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Check endpoint connectivity; fallback to /health if /demo/limited 404s on stub
        try:
            probe = await client.get(target_url)
            if probe.status_code == 404 and args.endpoint == "/demo/limited":
                health_probe = await client.get(f"{base_url}/health")
                if health_probe.status_code == 200:
                    target_url = f"{base_url}/health"
        except Exception:
            # Fallback for docker dev container probe
            pass

        if args.scenario == "all":
            for name, scen_runner in SCENARIO_MAP.items():
                sys.stderr.write(f"\n--- Running scenario: {name} ---\n")
                await scen_runner(client, target_url, {})
                await asyncio.sleep(0.5)
        else:
            runner: ScenarioFunc = SCENARIO_MAP[args.scenario]
            await runner(client, target_url, {})


if __name__ == "__main__":
    asyncio.run(main())
