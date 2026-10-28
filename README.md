# Production Rate Limiters in Redis & Python

A comprehensive, production-grade reference architecture for building, deploying, and observing rate limiters in distributed systems. Features 6 core rate limiting algorithms implemented in atomic Redis Lua scripts, 5 production policy compositions, interactive terminal traffic visualizers, Prometheus/Grafana dashboards, and live chaos testing.

```
                           Incoming Client Request
                                      │
                         [ 1 · IDENTITY RESOLVER ]
                    (Bearer Token, API Key, Client IP)
                                      │
                         [ 2 · SHADOW / ALLOWLIST ]
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
            Allowlisted                              Active Evaluator
        (Bypass to Upstream)                               │
                                            [ 3 · ATOMIC REDIS ENGINE ]
                                            (GCRA / Token Bucket Lua)
                                                           │
                                        ┌──────────────────┴──────────────────┐
                                        ▼                                     ▼
                                  Redis Healthy                           Redis Outage
                                        │                                     │
                             ┌──────────┴──────────┐              [ 5 · FAILURE MODE TRIAGE ]
                             ▼                     ▼              ┌───────────┼───────────┐
                          Admitted              Exceeded          ▼           ▼           ▼
                         (200 + TAT)         (429 + Retry)    Fail-Open  Fail-Closed  Local Bucket
                             │                     │          (200 + Log)  (503 Err)   (In-Memory)
                             └──────────┬──────────┘              │           │           │
                                        ▼                         └───────────┼───────────┘
                           [ 4 · STANDARD HEADERS ]                           ▼
                        RateLimit-Limit / Remaining / Reset             Upstream Route
```

---

## 1. Choose Your Rate Limiter in 30 Seconds

| If your primary constraint is... | Use this Algorithm | Directory | Redis Memory | Key Advantage |
|---|---|---|---|---|
| **Maximum simplicity, rough limits** | Fixed Window Counter | [`algorithms/01_fixed_window`](rate_limiters/algorithms/01_fixed_window) | $O(1)$ string key | Lowest CPU, trivial `INCR` |
| **Zero burst tolerance, 100% precision** | Sliding Window Log | [`algorithms/02_sliding_window_log`](rate_limiters/algorithms/02_sliding_window_log) | $O(\text{limit})$ ZSET | Exact history, no window drift |
| **High throughput at edge, bounded memory** | Sliding Window Counter | [`algorithms/03_sliding_window_counter`](rate_limiters/algorithms/03_sliding_window_counter) | $O(1)$ (2 ints) | 99.5% accuracy with 2 counters |
| **Classic burst + steady rate refill** | Token Bucket | [`algorithms/04_token_bucket`](rate_limiters/algorithms/04_token_bucket) | $O(1)$ hash | Intuitive capacity and refill |
| **Production standard (RECOMMENDED)** | **GCRA (Leaky Bucket)** | [`algorithms/05_gcra`](rate_limiters/algorithms/05_gcra) | **$O(1)$ single string** | **Zero workers, exact `Retry-After`** |
| **Protecting worker pools & long jobs** | Concurrency Limiter | [`algorithms/06_concurrency`](rate_limiters/algorithms/06_concurrency) | $O(\text{concurrency})$ ZSET | Auto-expiring leases, deadlock-free |

---

## 2. Repository Map

```text
rate_limiters/
├── algorithms/
│   ├── 01_fixed_window/             # Simple atomic counter (demonstrates boundary spike)
│   ├── 02_sliding_window_log/       # Precision timestamp ZSET (demonstrates race conditions)
│   ├── 03_sliding_window_counter/   # Cloudflare-style hybrid 2-counter approximation
│   ├── 04_token_bucket/             # Atomic token bucket with fractional refill math
│   ├── 05_gcra/                     # Production GCRA Theoretical Arrival Time (TAT) engine
│   └── 06_concurrency/              # In-flight lease limiter with automatic TTL expiry
├── policies/
│   ├── 01_multi_rule/               # Atomic multi-tier evaluation (sec + hour) with violated-rule reporting
│   ├── 02_identity_strategies/      # Pluggable identity resolvers (IP, API Key, Tenant, Dual Key)
│   ├── 03_weighted_cost/            # Non-uniform costs, LLM estimate-then-refund settlements
│   ├── 04_failure_modes/            # Fail-open, fail-closed, and local in-memory fallback during outages
│   └── 05_shadow_mode/              # Shadow observation, allowlist bypass, zero-code-change rollout
├── docs/
│   ├── 01-axes-and-architecture.md  # The six architectural rate limiter decisions
│   ├── 02-algorithms.md             # In-depth algorithmic derivations and trade-off tables
│   ├── 03-lua-vs-client-and-production.md # Production checklist, clustering, and Lua atomicity
│   ├── 04-use-case-recipes.md       # 10 production recipes ("I'm building X")
│   ├── 05-resources.md              # Curated reading list and canonical papers
│   └── 06-glossary.md               # Complete terminology reference
└── tools/
    ├── traffic/                     # Scripted traffic generator (steady, burst, abuse scenarios)
    ├── viz/                         # Live terminal timeline visualizer
    └── redis_inspect/               # Deep inspection of Redis keys, TTLs, and TAT structures
```

---

## 3. Quick Start: See It Work in 60 Seconds

### Prerequisites
- Docker and Docker Compose (V2)
- Make (optional, direct docker commands provided)

### 1. Launch a Subproject
Start the GCRA rate limiter and healthy Redis backend:
```bash
make up P=gcra
# Or: docker compose --profile gcra up --build -d
```

### 2. Stream Live Traffic
Run scripted traffic scenarios through the container and watch real-time admission decisions:
```bash
make demo P=gcra
# Or: docker compose run --rm dev python -m tools.traffic --project gcra --scenario all
```

### 3. Inspect Redis Internals
Peek into the internal Redis keys, Theoretical Arrival Time (TAT), and TTLs in real-time:
```bash
make inspect
# Or: docker compose run --rm dev python -m tools.redis_inspect
```

---

## 4. Recommended Study Order

| Step | Study / Execute | What You Learn |
|---|---|---|
| **1** | [`docs/01-axes-and-architecture.md`](docs/01-axes-and-architecture.md) | The six core decisions every rate limiter architecture must make. |
| **2** | [`docs/02-algorithms.md`](docs/02-algorithms.md) | Trade-offs across counters, sliding windows, buckets, and GCRA. |
| **3** | [`algorithms/01_fixed_window`](rate_limiters/algorithms/01_fixed_window) | Run the `boundary` scenario to witness the $2\times$ boundary surge. |
| **4** | [`algorithms/02_sliding_window_log`](rate_limiters/algorithms/02_sliding_window_log) | Run `race_demo.py` to observe client check-and-set race conditions live. |
| **5** | [`algorithms/05_gcra`](rate_limiters/algorithms/05_gcra) | The mathematical single-key TAT trick powering modern API gateways. |
| **6** | [`algorithms/06_concurrency`](rate_limiters/algorithms/06_concurrency) | Why in-flight concurrency differs from time-window rate limiting. |
| **7** | [`policies/01` $\to$ `05`](rate_limiters/policies) | Composing real-world rules: multi-tier, identity, cost, failover, shadow mode. |
| **8** | [`policies/04_failure_modes`](rate_limiters/policies/04_failure_modes) | Run `make chaos` to stop Redis mid-traffic and verify auto-recovery. |
| **9** | [`docs/04-use-case-recipes.md`](docs/04-use-case-recipes.md) | Pick the exact configuration for your application architecture. |
| **10** | [`docs/05-resources.md`](docs/05-resources.md) | Dive deeper into canonical engineering posts from Stripe, Cloudflare, and Figma. |

---

## 5. How to Plug a Limiter into Your Own App (in 5 Minutes)

Copy `rate_limiters/algorithms/05_gcra/app` into your FastAPI or Starlette application:

### 1. Register Dependencies
```python
import redis.asyncio as aioredis
from fastapi import FastAPI, Depends, Request
from app.repositories.redis_repository import RedisRepository
from app.services.rate_limiter_service import RateLimiterService
from app.controllers.rate_limit_controller import RateLimitController

app = FastAPI()
redis_client = aioredis.from_url("redis://localhost:6379/0")
repository = RedisRepository(redis_client)
service = RateLimiterService(repository)
limiter = RateLimitController(service)
```

### 2. Protect Your Endpoints
```python
# Limit: 10 requests per 60 seconds with burst capacity of 10
@app.get("/items", dependencies=[Depends(limiter.require_rate_limit(limit=10, period=60, burst=10))])
async def read_items():
    return {"status": "ok", "items": ["item1", "item2"]}
```

When quota is exhausted, the controller automatically responds with standard headers:
```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
RateLimit-Limit: 10
RateLimit-Remaining: 0
RateLimit-Reset: 14
Retry-After: 14

{
  "error": "rate_limited",
  "rule": "std",
  "retry_after_seconds": 14
}
```

---

## 6. Running Tests & Quality Verification

Run the comprehensive test matrix and linters inside Docker without installing dependencies on your host machine:

```bash
# Run unit tests for a specific project
make test P=rate_limiters/algorithms/05_gcra

# Run full linting suite (ruff + mypy across all 11 subprojects)
make lint

# Run universal HTTP contract tests against an active container
docker compose run --rm dev pytest tests/contract --target-url http://gcra:8000 -v

# Run duplicate file drift guard
docker compose run --rm dev python tools/check_duplicates.py
```

---

## 7. Observability: Dashboards & Key Inspection

Launch the bundled Prometheus and Grafana stack:
```bash
make observe
```
- **Grafana:** `http://localhost:3000` (pre-configured dashboard visualizing allowed vs denied requests, p50/p99 decision latencies, and fail-open counters)
- **Prometheus:** `http://localhost:9090`
- **RedisInsight:** `make tools` $\to$ browse keys and memory live on `http://localhost:5540`
