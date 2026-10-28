# Policy 05: Shadow Mode & Allowlist (Safe Rollout)

A production rate limiter policy based on the Generic Cell Rate Algorithm (GCRA) designed for **risk-free limit rollouts**. Supports three operating modes: **Shadow Mode (dry-run)**, **Enforcement Mode**, and **Allowlist Bypass**.

---

## 1. Mental Model: The Rollout Danger

Introducing a rate limit directly into production in **Enforce** mode is dangerous:
> *Without shadow mode, week 1 is a surprise outage for your largest enterprise customer whose integration had a bursty batch job you didn't know about.*

The safe rollout lifecycle uses **Shadow Mode** first:

```
                  ┌────────────────────────────────────────────────────────┐
                  │ Week 1: Shadow Mode                                    │
                  │ All requests return 200 OK.                            │
                  │ Dashboard reveals: "3.2% would be blocked (Customer A)"│
                  └─────────────────────────┬──────────────────────────────┘
                                            │ Reach out to Customer A / tune limits
                                            ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Week 2: Shadow Mode                                    │
                  │ Dashboard confirms: "0.02% would be blocked"           │
                  └─────────────────────────┬──────────────────────────────┘
                                            │ Flip mode to Enforce (Zero Code Change)
                                            ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Week 3: Enforce Mode                                   │
                  │ Over-quota requests blocked with 429 Too Many Requests │
                  └────────────────────────────────────────────────────────┘
```

---

## 2. Operating Modes & Behavior

| Mode | Response Code | RateLimit Headers | Metrics Recorded | Downstream Redis Call |
|---|---|---|---|---|
| **Shadow (Within Quota)** | `200 OK` | `X-RateLimit-Mode: shadow`<br>`X-RateLimit-Action: allowed` | `rl_decisions_total{status="shadow",outcome="allowed"}` | Yes (GCRA evaluated) |
| **Shadow (Quota Exceeded)** | `200 OK` *(Not blocked!)* | `X-RateLimit-Mode: shadow`<br>`X-RateLimit-Action: shadow_denied`<br>`X-RateLimit-Would-Block: true` | `rl_shadow_denied_total`<br>`rl_decisions_total{status="shadow",outcome="shadow_denied"}` | Yes (GCRA evaluated) |
| **Enforce (Within Quota)** | `200 OK` | `X-RateLimit-Mode: enforce`<br>`X-RateLimit-Action: allowed` | `rl_decisions_total{status="enforce",outcome="allowed"}` | Yes (GCRA evaluated) |
| **Enforce (Quota Exceeded)** | `429 Too Many Requests` | `X-RateLimit-Mode: enforce`<br>`X-RateLimit-Action: denied`<br>`Retry-After: <seconds>` | `rl_decisions_total{status="enforce",outcome="denied"}` | Yes (GCRA evaluated) |
| **Allowlist** | `200 OK` | `X-RateLimit-Mode: allowlist`<br>`X-RateLimit-Action: bypassed` | `rl_bypassed_total`<br>`rl_decisions_total{status="allowlist",outcome="bypassed"}` | **No (Redis bypassed)** |

---

## 3. Allowlist Bypass (Zero-Cost Internal Traffic)

Trusted clients (internal healthcheck probes, Kubernetes sidecars, cron workers, admin keys) should **never** consume rate limiter capacity, nor should they add network round-trips to Redis.

In `app/services/rate_limiter_service.py`:
```python
if self.is_allowlisted(identity):
    record_decision("shadow_mode", outcome="bypassed", status="allowlist")
    return Decision(allowed=True, action="bypassed", mode="allowlist", ...)
```

Allowlist matches configured identities (`user:admin`, `ip:127.0.0.1`, `system:*`) in-memory before any Redis command is issued.

---

## 4. Zero-Downtime Mode Flipping

Flipping from Shadow to Enforce mode requires **no redeployment** and **no code changes**:

- **Environment Setting:** `RL_MODE=shadow` (or `RL_MODE=enforce`)
- **Runtime Admin Toggle:**
  ```bash
  # Check current mode
  curl http://localhost:8205/admin/mode

  # Flip to enforce mode dynamically
  curl -X POST "http://localhost:8205/admin/mode?mode=enforce"
  ```

---

## 5. See It Work

### 1. Calm Traffic
```bash
make up P=shadow-mode
docker compose run --rm dev python -m tools.traffic --project shadow-mode --scenario steady
```

### 2. Burst Then Abuse
```bash
docker compose run --rm dev python -m tools.traffic --project shadow-mode --scenario burst
```

### 3. Safe Rollout Drill
Run the end-to-end rollout demonstration:
```bash
./rate_limiters/policies/05_shadow_mode/scripts/rollout_drill.sh
```

Or manually observe shadow mode letting through over-quota requests:
```bash
# Rapid burst (exceeding burst limit of 5)
for i in {1..8}; do
  curl -i -H "X-User-Id: alice" http://localhost:8205/demo/shadow
done
# Notice: All requests return 200 OK!
# Starting from request 6, response includes:
#   X-RateLimit-Action: shadow_denied
#   X-RateLimit-Would-Block: true
#   X-RateLimit-Retry-After: 2
```
