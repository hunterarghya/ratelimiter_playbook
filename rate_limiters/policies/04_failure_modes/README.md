# Policy 04: Failure Modes & Degradation Strategies

A production rate limiter policy demonstrating how to survive cache and coordination infrastructure outages (Redis down, network partition, or failover) without cascading system failure.

Supports route-level failure policies: **Fail-Open**, **Fail-Closed**, and **Local In-Memory Fallback**, with automatic recovery when Redis returns.

---

## 1. Mental Model

A rate limiter sits on the critical path of every incoming request. When the rate-limiter store (Redis) fails or becomes unreachable:

> **The worst possible outcome is for the rate limiter itself to take down the entire application by hanging on connection timeouts.**

Instead, each route or API category must explicitly choose its degradation policy:

```
                          Incoming Request
                                 │
                         Try Redis GCRA
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
               Redis Healthy             Redis Down
                     │                       │
              Standard GCRA           Failure Policy
               (200 or 429)                  │
                         ┌───────────────────┼───────────────────┐
                         ▼                   ▼                   ▼
                     Fail-Open          Fail-Closed         Local Fallback
                 (High Availability) (Downstream Safety)  (Best-Effort Guard)
                         │                   │                   │
                     HTTP 200            HTTP 503           In-Memory Bucket
                 (Increment Metric)   (Service Unavail)     (200 then 429)
```

| Strategy | Trade-off | Ideal Use Case | Client Behavior |
|---|---|---|---|
| **Fail-Open** | Prioritizes **availability** over strict limits. Downstream services may receive extra traffic. | Read-only endpoints, public catalog, search, status pages | `200 OK`, `X-RateLimit-Source: fail_open` |
| **Fail-Closed** | Prioritizes **integrity** and backend safety over client availability. | Payment processing, DB-heavy mutations, bulk exports, LLM generation | `503 Service Unavailable`, `X-RateLimit-Source: fail_closed` |
| **Local Fallback** | Enforces an approximate **per-process in-memory token bucket** during the outage. | Critical APIs with multiple app instances, balancing load and protection | `200 OK` until local bucket empty, then `429 Too Many Requests` |

---

## 2. Fast Socket Timeouts

If Redis is unreachable or network packets drop, default TCP connection timeouts (30 to 60 seconds) will exhaust the ASGI worker pool, halting all traffic.

In `app/main.py`:
```python
redis_client = redis.from_url(
    settings.redis_url,
    socket_timeout=float(settings.rl_redis_timeout_ms) / 1000.0,      # 50 ms
    socket_connect_timeout=float(settings.rl_redis_timeout_ms) / 1000.0,
)
```

A tight timeout (e.g. 50ms) ensures that cache degradation decisions execute in milliseconds, preserving application throughput.

---

## 3. Metrics & Observability

When running fail-open, ops teams must be alerted immediately that limits are not being enforced.

- `rl_fail_open_total{limiter="failure_modes"}`: Incremented every time a request is admitted due to fail-open policy.
- `rl_decisions_total{limiter="failure_modes", outcome="allowed", status="fail_open"}`
- `rl_decisions_total{limiter="failure_modes", outcome="denied", status="fail_closed"}`
- `rl_decisions_total{limiter="failure_modes", outcome="allowed|denied", status="local_fallback"}`

---

## 4. Automatic Recovery

When Redis is restored:
- `redis-py` connection pools automatically reconnect on the next request.
- No manual restart of application pods or containers is required.
- Transitions back to `X-RateLimit-Source: redis` seamlessly.

---

## 5. See It Work

### 1. Calm Traffic
```bash
make up P=failure-modes
docker compose run --rm dev python -m tools.traffic --project failure-modes --scenario steady
```

### 2. Burst Then Abuse
```bash
docker compose run --rm dev python -m tools.traffic --project failure-modes --scenario burst
```

### 3. Chaos Drill: Redis Outage Mid-Traffic
Stop Redis mid-flight to see degradation policies activate in real-time, then restart Redis to verify auto-recovery:

```bash
# Run the chaos drill
./rate_limiters/policies/04_failure_modes/scripts/chaos.sh
```

Or step-by-step:
```bash
# 1. Stop Redis
docker compose stop redis

# 2. Test Fail-Open (returns 200 OK)
curl -i -H "X-User-Id: alice" http://localhost:8204/demo/fail-open

# 3. Test Fail-Closed (returns 503 Service Unavailable)
curl -i -H "X-User-Id: alice" http://localhost:8204/demo/fail-closed

# 4. Test Local Fallback (allows initial tokens, then returns 429)
curl -i -H "X-User-Id: alice" http://localhost:8204/demo/fallback

# 5. Restart Redis (recovers with zero downtime)
docker compose start redis
curl -i -H "X-User-Id: alice" http://localhost:8204/demo/fail-open
```
