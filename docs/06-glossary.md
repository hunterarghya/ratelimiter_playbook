# 06 · The Rate Limiting Glossary

An authoritative, comprehensive reference defining every core term, algorithmic symbol, and operational concept used across this repository.

---

### **A**

#### **Allowlist Bypass**
A policy whereby trusted identities (e.g., internal microservices, Kubernetes health probes, synthetic monitoring agents, or administrative tokens) skip rate limiting completely. Allowlisted requests bypass Redis calls entirely (`bypassed`), consuming zero network overhead and leaving customer quotas untouched.
*Reference project:* [`rate_limiters/policies/05_shadow_mode`](../rate_limiters/policies/05_shadow_mode)

#### **Atomicity**
The guarantee that an evaluation sequence (read state $\to$ calculate eligibility $\to$ update state) executes as an indivisible unit. In Redis, atomicity is achieved by executing logic inside single-threaded Lua scripts, preventing race conditions where concurrent requests over-admit traffic.
*Reference project:* [`rate_limiters/algorithms/05_gcra`](../rate_limiters/algorithms/05_gcra)

---

### **B**

#### **Boundary Spike (Fixed Window 2× Surge)**
A structural vulnerability inherent to the Fixed Window Counter algorithm. A client can send its entire quota at the final millisecond of Window 1, and send another full quota at the first millisecond of Window 2. Across the 2-second boundary window, the backend experiences $2\times$ the configured limit.
*Reference project:* [`rate_limiters/algorithms/01_fixed_window`](../rate_limiters/algorithms/01_fixed_window)

#### **Burst Capacity ($\tau$ / Tau)**
The maximum quantity of traffic an identity can emit instantaneously without being throttled.
- In **Token Bucket**, $\tau$ corresponds to the maximum bucket capacity.
- In **GCRA**, $\tau$ is the burst tolerance in time units: $\tau = T \times \text{burst}$.

---

### **C**

#### **Clock Drift**
Discrepancies between application server wall clocks and the Redis server clock. If application servers pass client timestamps to Redis, clock skew can cause premature allowance or unfair throttling. Production scripts eliminate drift by querying the Redis internal clock directly via `redis.call('TIME')`.

#### **Concurrency Limiter**
A protective barrier that measures and caps **simultaneous in-flight operations** (e.g., max 5 parallel database exports) rather than request frequency over time. Uses auto-expiring leases to guarantee slot recovery if workers crash.
*Reference project:* [`rate_limiters/algorithms/06_concurrency`](../rate_limiters/algorithms/06_concurrency)

#### **Cost (Request Weight)**
A multiplier reflecting the computational, memory, or financial expense of an operation. Standard requests cost 1; heavy analytical queries or LLM token generations cost $N > 1$.
*Reference project:* [`rate_limiters/policies/03_weighted_cost`](../rate_limiters/policies/03_weighted_cost)

---

### **E**

#### **Emission Interval ($T$)**
In the Generic Cell Rate Algorithm (GCRA), the theoretical interval between requests at the nominal steady-state rate:
$$T = \frac{\text{period}}{\text{limit}}$$
For an API allowing 10 requests per second, the emission interval $T$ is 100 milliseconds.

#### **Enforcement Mode**
The standard operating mode of a rate limiter where policy violations actively block requests with `HTTP 429 Too Many Requests` and include a `Retry-After` header.
*Reference project:* [`rate_limiters/policies/05_shadow_mode`](../rate_limiters/policies/05_shadow_mode)

#### **Estimate-Then-Refund**
A pattern for handling operations whose true cost is only known after execution (such as LLM generation or faceted database searches). The system reserves an estimated maximum cost upfront, runs the operation, and refunds unused capacity back into the rate limiter upon completion.
*Reference project:* [`rate_limiters/policies/03_weighted_cost`](../rate_limiters/policies/03_weighted_cost)

#### **EVAL / EVALSHA**
Redis commands for invoking Lua scripts. `EVAL` sends the script text across the network on every invocation. `EVALSHA` sends only the 40-character SHA1 digest of a pre-loaded script. Production libraries automatically use `EVALSHA` and fall back to `EVAL` on `NOSCRIPT` cache misses.

---

### **F**

#### **Fail-Closed**
A degradation policy where the application rejects traffic (`HTTP 503 Service Unavailable`) if the rate limiter backend (Redis) is down. Used for operations where downstream protection and financial integrity supersede client availability (e.g., checkout, money transfers, LLM GPU generation).
*Reference project:* [`rate_limiters/policies/04_failure_modes`](../rate_limiters/policies/04_failure_modes)

#### **Fail-Open**
A degradation policy where the application admits traffic (`HTTP 200 OK`) if the rate limiter backend is down. Used for high-availability read paths (e.g., public catalog browsing, landing pages). Must increment an alert metric (`rl_fail_open_total`) to notify on-call engineers.
*Reference project:* [`rate_limiters/policies/04_failure_modes`](../rate_limiters/policies/04_failure_modes)

---

### **G**

#### **GCRA (Generic Cell Rate Algorithm)**
A leaky-bucket variant originally standardized for Asynchronous Transfer Mode (ATM) networks. Instead of tracking tokens, GCRA models traffic as a single timestamp: the **Theoretical Arrival Time (TAT)**. It requires only one Redis string key, executes in $O(1)$ time, and yields mathematically exact `Retry-After` durations.
*Reference project:* [`rate_limiters/algorithms/05_gcra`](../rate_limiters/algorithms/05_gcra)

---

### **H**

#### **Hash Tag**
In Redis Cluster, enclosing a substring within curly braces `{...}` forces Redis to hash only that enclosed portion to calculate the cluster slot. For example:
- `rl:{user:42}:sec`
- `rl:{user:42}:hour`
Both keys map to the exact same cluster node, allowing atomic multi-key Lua scripts without raising `CROSSSLOT` errors.

#### **Hot Key**
A Redis key that receives a disproportionate volume of commands (e.g., a shared key for unauthenticated global traffic), concentrating load onto a single Redis thread and driving up latency. Mitigated by client-side local caching, key salting, or hierarchical partitioning.

---

### **L**

#### **Lease**
A unique token representing an allocated slot in a concurrency limiter. Every lease is granted with a Time-To-Live (TTL). If the holder worker process crashes before calling `release()`, the lease automatically expires in Redis, freeing the slot for other callers.
*Reference project:* [`rate_limiters/algorithms/06_concurrency`](../rate_limiters/algorithms/06_concurrency)

#### **Local Fallback**
An in-memory rate limiter running inside each application process that activates automatically during Redis outages. Provides best-effort protection to prevent downstream services from being overwhelmed by infinite unthrottled traffic.
*Reference project:* [`rate_limiters/policies/04_failure_modes`](../rate_limiters/policies/04_failure_modes)

---

### **P**

#### **PX / PTTL**
Redis commands for managing millisecond-precision key expiration.
- `PEXPIRE key 1500`: Sets key expiry to 1,500 milliseconds.
- `PTTL key`: Returns remaining key lifetime in milliseconds.

---

### **R**

#### **Reset Time (`RateLimit-Reset`)**
The duration (in integer seconds) until a rate limit bucket completely drains, returns to full capacity, or begins a new quota window.

#### **Retry-After**
A standard HTTP header defined by RFC 7231 and RFC 6585. Indicates to a throttled client exactly how many seconds it must sleep before retrying.

---

### **S**

#### **Shadow Mode (Dry-Run)**
An observation mode where the rate limiter evaluates incoming traffic and records would-be rejections (`shadow_denied` metric and log entry), but **does not block the client** (`200 OK` is returned). Allows engineering teams to audit limit impact before switching to active enforcement.
*Reference project:* [`rate_limiters/policies/05_shadow_mode`](../rate_limiters/policies/05_shadow_mode)

#### **Sliding Window Counter**
A hybrid algorithm that stores request counts in two integer keys (the current window and the previous window). Estimates current traffic by computing an overlap percentage. Requires only $O(1)$ memory and offers smooth burst mitigation.
*Reference project:* [`rate_limiters/algorithms/03_sliding_window_counter`](../rate_limiters/algorithms/03_sliding_window_counter)

#### **Sliding Window Log**
An algorithm that records a timestamp for every individual request in a Redis Sorted Set (ZSET). Provides 100% mathematical precision at the expense of $O(\text{limit})$ memory per key.
*Reference project:* [`rate_limiters/algorithms/02_sliding_window_log`](../rate_limiters/algorithms/02_sliding_window_log)

---

### **T**

#### **TAT (Theoretical Arrival Time)**
In GCRA, the hypothetical timestamp at which the next request should arrive if traffic flowed at a perfectly uniform rate.
- If $\text{now} \ge \text{TAT} - \tau$, the request is **admitted**, and TAT advances by $T$.
- If $\text{now} < \text{TAT} - \tau$, the request is **denied**, and TAT remains unchanged.
*Reference project:* [`rate_limiters/algorithms/05_gcra`](../rate_limiters/algorithms/05_gcra)

#### **Thundering Herd**
A failure scenario where hundreds or thousands of clients, having been simultaneously rate-limited, all wake up and retry at the exact same millisecond when the quota window resets. Prevented by returning continuous GCRA `Retry-After` intervals or mandating randomized client jitter.

#### **Token Bucket**
A classic rate limiting algorithm where tokens accumulate in a bucket of capacity $C$ at a constant refill rate $R$. Each incoming request consumes one or more tokens. If insufficient tokens are present, the request is throttled.
*Reference project:* [`rate_limiters/algorithms/04_token_bucket`](../rate_limiters/algorithms/04_token_bucket)

---

### **Z**

#### **ZSET (Sorted Set)**
A Redis data structure containing unique string members ordered by a floating-point score. Used by the Sliding Window Log algorithm to index request timestamps and purge expired entries via `ZREMRANGEBYSCORE`.
*Reference project:* [`rate_limiters/algorithms/02_sliding_window_log`](../rate_limiters/algorithms/02_sliding_window_log)
