# Policy 02: Identity Strategies

A production-grade rate limiting policy supporting pluggable, multi-tiered identity resolution strategies (IP address, authenticated User ID, hashed API Key, Tenant / Organization ID, Endpoint, Global system capacity, and Composite IP + User) with defense against `X-Forwarded-For` spoofing and seamless anonymous-to-authenticated transitions.

---

## 1. Mental Model

A rate limiter is only as effective as the identity key it tracks. If an attacker can manipulate their identity, they can bypass any quota. If legitimate users share a single NAT gateway IP, a naive IP-based limiter inadvertently throttles entire office buildings or mobile carrier cells.

```
                           Incoming Request
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
          Unauthenticated                    Authenticated
        (IP Address Strategy)             (User / Key / Tenant)
                  │                               │
        X-Forwarded-For Defense           Hash Secret API Keys
       (Extract trusted rightmost)         (Never leak in Redis)
                  │                               │
                  └───────────────┬───────────────┘
                                  ▼
                   Multi-Target Atomic GCRA Lua
                     (Check All, Charge All)
```

---

## 2. Supported Identity Strategies

| Strategy | Key Pattern | Resolution Source | Use Case |
|---|---|---|---|
| **IP Address** | `rl:{ip:<ip>}:...` | Rightmost trusted proxy from `X-Forwarded-For` or client socket IP | Public unauthenticated APIs, DDoS mitigation |
| **User ID** | `rl:{user:<id>}:...` | `X-User-Id` or verified JWT claim `sub` | Logged-in user accounts, fair share per customer |
| **API Key** | `rl:{key:<sha256>}:...` | `X-API-Key` hashed with SHA-256 | Developer APIs, machine-to-machine integrations |
| **Tenant / Org** | `rl:{tenant:<id>}:...` | `X-Tenant-Id` header or organization context | B2B SaaS multi-tenant isolation |
| **Endpoint** | `rl:{endpoint:<method>:<path>:ip:<ip>}:...` | HTTP method + URL route + IP | Protecting expensive routes (e.g. `/checkout`, `/search`) |
| **Global** | `rl:{global:all}:...` | Constant string `global:all` | Total system capacity ceiling protecting downstream DB |
| **Composite (IP+User)** | `rl:{composite:ip:<ip>:user:<user>}:...` | Combined tuple of IP and User | Credential stuffing defense, concurrent session throttling |

---

## 3. `X-Forwarded-For` Spoofing Defense

### The Threat
When clients make HTTP requests through reverse proxies (load balancers, CDNs like Cloudflare/Fastly, or NGINX), each proxy appends the socket IP of the sender to the comma-separated `X-Forwarded-For` (XFF) header.
A malicious client can send:
```http
X-Forwarded-For: 1.1.1.1, 8.8.8.8
```
If your rate limiter takes the **first** (leftmost) IP (`1.1.1.1`), the attacker can rotate this forged IP on every request and completely bypass rate limits.

### The Defense: Trusted Proxy Traversal
Never trust arbitrary leftmost entries. You must configure the number of trusted reverse proxies between the public internet and your application (`RL_TRUSTED_PROXY_COUNT`):

```python
parts = [p.strip() for p in xff.split(",") if p.strip()]
if len(parts) >= trusted_proxy_count:
    # Take the IP appended by our outermost trusted ingress proxy:
    client_ip = parts[-trusted_proxy_count]
else:
    client_ip = parts[0]
```

Example with 2 trusted proxies (e.g., Cloudflare $\to$ NGINX $\to$ App):
```
Header received:  [spoofed_ip, 203.0.113.5, 172.68.1.1]
Index from right:         [-3]          [-2]        [-1]
Selected Client IP: 203.0.113.5 (parts[-2])
```

---

## 4. API Key Privacy via SHA-256 Hashing

Never use raw API secret keys (such as `sk_live_abcdef123456`) directly as Redis keys:
1. Redis commands (`KEYS`, `MONITOR`, slow logs) and Redis state dumps would expose client secrets in plaintext to internal operators.
2. Inadvertent telemetry or debug endpoints could leak live keys.

This policy computes `hashlib.sha256(raw_key.encode()).hexdigest()` and prefixes the Redis key with `key:<hex64>`.

---

## 5. Anonymous to Authenticated Transition Policy

A critical UX requirement is handling the transition when an anonymous visitor on a shared IP (e.g., university Wi-Fi or corporate NAT) logs in:

1. **Anonymous Mode**: Evaluated strictly against the anonymous IP quota (`ip_tier`). When shared IP quota runs dry, unauthenticated requests receive `429 Too Many Requests`.
2. **Authenticated Mode**: Upon successful authentication, the request presents an `X-User-Id` (or auth token). The request is now evaluated against the user's dedicated quota (`user_tier`).
3. **Transition Route (`/demo/transition`)**: Legitimate authenticated users are not locked out merely because someone else on the same public Wi-Fi exhausted the anonymous IP quota.

---

## 6. Redis Cluster Caveats & Hash Tags

In Redis Cluster, all keys passed to a multi-key Lua script (`EVAL` / `EVALSHA`) **must hash to the exact same cluster hash slot**. Redis enforces this via hash tags: `{...}`.

| Multi-Identity Scenario | Same Slot Possible? | Atomic Lua Viable? | Production Solution |
|---|---|---|---|
| **Same Identity + Multiple Rules** (e.g., User Per-Sec + User Per-Hour) | ✅ Yes: `rl:{user:alice}:sec` & `rl:{user:alice}:hour` | ✅ Fully Atomic | Put the identity in the hash tag `{user:alice}` |
| **Composite IP + User** | ✅ Yes: `rl:{comp:1.2.3.4:alice}:...` | ✅ Fully Atomic | Single composite key in hash tag |
| **Independent IP AND User in Cluster** | ❌ No: `{ip:1.2.3.4}` and `{user:alice}` map to different cluster slots | ❌ Cross-slot Lua error | **Sequential evaluation** (eval IP, then eval User) or assign a common route/tenant tag (with hot shard trade-off) |
| **Standalone / Sentinel Redis** | ✅ Yes | ✅ Fully Atomic | Works natively across any set of keys |

---

## 7. Redis Key Schema

```
rl:{<identity>}:<rule_name>:gcra
```
- Type: `String` storing integer TAT in Unix milliseconds.
- TTL: Automatically set to `ceil((burst * period) / limit) + 1` seconds.

---

## 8. HTTP Contract & Headers

### Allowed Response (200 OK)
```http
HTTP/1.1 200 OK
RateLimit-Limit: 10
RateLimit-Remaining: 9
RateLimit-Reset: 1
X-RateLimit-Identity: user:alice
```

### Rate Limited Response (429 Too Many Requests)
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 4
RateLimit-Limit: 10
RateLimit-Remaining: 0
RateLimit-Reset: 4
Content-Type: application/json

{
  "detail": {
    "error": "rate_limited",
    "rule": "user:alice:user_tier",
    "retry_after_seconds": 4,
    "identity": "user:alice"
  }
}
```

---

## 9. Quickstart

Run via Docker:
```bash
# Start Redis and Identity service
docker compose --profile identity up --build -d identity

# Inspect health
curl http://localhost:8202/health
```

---

## 10. See It Work

### 1. Steady & All Identities Demo
```bash
./rate_limiters/policies/02_identity_strategies/scripts/demo.sh
```

### 2. Concurrency Race & Quota Burn Demo
```bash
docker compose run --rm dev python rate_limiters/policies/02_identity_strategies/scripts/race_demo.py
```

### 3. Inspect Redis State
```bash
curl -s "http://localhost:8202/debug/state" | jq
```

---

## 11. Code Tour

- [`app/services/identity.py`](app/services/identity.py): Pluggable identity resolvers (`ip`, `user`, `api_key`, `tenant`, `endpoint`, `global`, `composite`).
- [`app/lua/identity_gcra.lua`](app/lua/identity_gcra.lua): Two-phase GCRA script supporting atomic multi-identity checks.
- [`app/controllers/rate_limit_controller.py`](app/controllers/rate_limit_controller.py): Translates HTTP requests and headers into rate limit evaluations.
- [`app/routes/demo.py`](app/routes/demo.py): Dedicated demonstration endpoints for each identity strategy.
- [`tests/test_unit_service.py`](tests/test_unit_service.py): Spoofing defense unit tests.
- [`tests/test_script_invariants.py`](tests/test_script_invariants.py): Real Redis tests for quota burn prevention and transitions.

---

## 12. Observability & Metrics

Prometheus metrics exposed at `/metrics`:
- `rl_decisions_total{limiter="identity_strategies", rule="<rule>", outcome="allowed|denied"}`
- `rl_latency_seconds{limiter="identity_strategies"}`
