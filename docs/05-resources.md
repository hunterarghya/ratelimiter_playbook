# 05 · Curated Resources & Annotated Reading Guide

A curated index of foundational engineering posts, standards specifications, and reference implementations for building production-grade rate limiters.

> **Verification Note:** Every external URL in this document was verified on **October 28, 2026**.

---

## 1. The Study Matrix: What to Read and When

| Stage | Document / Resource | Key Takeaway |
|---|---|---|
| **Before Writing Code** | [Stripe Engineering: Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters) | The 4 limiter types (Request, Concurrency, Usage, Cost) and real-world failure modes. |
| **Before Algorithm 03** | [Cloudflare: Counting things at scale](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/) | How sliding window counter math approximates logs with 2 integer counters. |
| **Before Algorithm 05** | [Brandur Leach: Rate Limiting, Cells, and GCRA](https://brandur.org/rate-limiting) | The mathematical derivation of the Theoretical Arrival Time (TAT) and single-key GCRA. |
| **Before Concurrency 06** | [Stripe: Concurrency Limiting](https://stripe.com/blog/rate-limiters#building-a-concurrency-limiter) | Why queue depth and in-flight request leases differ fundamentally from rate limits. |
| **Before Lua Projects** | [Redis Documentation: Lua API](https://redis.io/docs/latest/develop/interact/programmability/lua-api/) | Atomicity, `EVALSHA`, script caching, script replication, and clock access via `redis.call('TIME')`. |
| **Before Cluster Setup** | [Redis Cluster Specification: Hash Tags](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#hash-tags) | Using `{identity}` curly braces to pin multi-key evaluations to the same hash slot. |
| **Before Policy 04** | [Figma: An alternative approach to rate limiting](https://www.figma.com/blog/an-alternative-approach-to-rate-limiting/) | Local process caching, degradation policies, and preventing cascading failures. |
| **Before Production API** | [IETF Draft: RateLimit Header Fields](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers) | Standardized HTTP response header naming (`RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`). |

---

## 2. Canonical Engineering Blog Posts

### [Stripe Engineering: Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters)
- **Author:** Paul Tarjan
- **Context:** Stripe's architectural blueprint explaining how they protect core payment processing APIs.
- **Why It Matters:** Categorizes rate limiters into four distinct functional barriers:
  1. *Request Rate Limiter:* Caps request frequency (HTTP 429).
  2. *Concurrent Request Limiter:* Caps simultaneous in-flight connections (protects CPU/DB worker pools).
  3. *Fleet Usage Limiter:* Allocates fair shares of cluster capacity across tenants.
  4. *Cost Limiter:* Assigns non-uniform costs to expensive operations.

### [Brandur Leach: Rate Limiting, Cells, and GCRA](https://brandur.org/rate-limiting)
- **Author:** Brandur Leach (former Stripe infrastructure engineer)
- **Context:** The definitive tutorial on the Generic Cell Rate Algorithm (GCRA) adapted from ATM networks to web APIs.
- **Why It Matters:** Explains how tracking Theoretical Arrival Time (TAT) replaces the sliding window and token bucket with a single Redis string key and zero background workers.

### [Cloudflare: How we built rate limiting capable of scaling through millions of requests per second](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/)
- **Author:** John Graham-Cumming
- **Context:** How Cloudflare built edge rate limiting across globally distributed points of presence (PoPs).
- **Why It Matters:** Derives the sliding window counter approximation formula:
  $$\text{Count} = \text{Count}_{\text{current}} + \text{Count}_{\text{previous}} \times \left(1 - \frac{\text{elapsed}}{\text{window}}\right)$$
  Proves that 2 integer keys per client achieve 99.5% accuracy without storing individual request timestamps.

### [Figma: An alternative approach to rate limiting](https://www.figma.com/blog/an-alternative-approach-to-rate-limiting/)
- **Author:** Tony Jin
- **Context:** Real-world lessons from running collaborative multi-player state engines under massive sudden traffic spikes.
- **Why It Matters:** Explains why centralized Redis limiters can become single points of failure, motivating local in-memory token buckets, adaptive shedding, and graceful fail-open patterns.

---

## 3. RFC & Standards Specifications

### [IETF Draft: RateLimit Header Fields for HTTP](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers)
- Standardizes response headers across industry APIs:
  - `RateLimit-Limit`: Maximum requests permitted in current quota.
  - `RateLimit-Remaining`: Number of requests remaining in current quota window.
  - `RateLimit-Reset`: Number of seconds until quota window resets.
  - `RateLimit-Policy`: Quota definition (e.g. `10;w=60`).

### [RFC 6585: Additional HTTP Status Codes (Section 4: 429 Too Many Requests)](https://datatracker.ietf.org/doc/html/rfc6585#section-4)
- Formally defines HTTP status code `429 Too Many Requests`.
- Mandates inclusion of the `Retry-After` header when the client should back off for a known duration.

### [RFC 7231: HTTP/1.1 Semantics (Section 7.1.3: Retry-After)](https://datatracker.ietf.org/doc/html/rfc7231#section-7.1.3)
- Defines valid formatting for `Retry-After`: either an integer number of decimal seconds (e.g. `Retry-After: 30`) or an HTTP date (e.g. `Retry-After: Fri, 31 Dec 2026 23:59:59 GMT`). Integer seconds are overwhelmingly preferred for programmatic API clients.

---

## 4. Redis Documentation & Operational Guides

### [Redis Programmability & Lua Scripting API](https://redis.io/docs/latest/develop/interact/programmability/lua-api/)
- Essential reference for atomic operations:
  - Why Lua scripts are transactional and non-preemptive.
  - Difference between `EVAL` (transmits full script) and `EVALSHA` (transmits 40-character SHA1 hash).
  - Calling Redis clock: `redis.call('TIME')`.

### [Redis Cluster Specification: Hash Tags](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#hash-tags)
- Crucial for multi-key evaluation in Redis Cluster:
  - Any text enclosed in curly braces `{...}` forces keys to the exact same hash slot (e.g., `rl:{user:123}:sec` and `rl:{user:123}:hour`).
  - Without hash tags, multi-key Lua commands fail with `CROSSSLOT Keys in request don't hash to the same slot`.

---

## 5. Reference Open Source Implementations

| Project | Language | Architecture | Highlights |
|---|---|---|---|
| [`brandur/redis-cell`](https://github.com/brandur/redis-cell) | Rust | Redis Module | Implements GCRA as a native C-ABI command `CL.THROTTLE`. |
| [`go-redis/redis_rate`](https://github.com/go-redis/redis_rate) | Go | Lua Script | Minimalist, elegant GCRA in Lua for Go applications. |
| [`envoyproxy/ratelimit`](https://github.com/envoyproxy/ratelimit) | Go | gRPC Microservice | Production-grade descriptor engine powering Envoy service meshes. |
| [`alisaifee/limits`](https://github.com/alisaifee/limits) | Python | Library | Pluggable storage backends (Redis, Memcached, Memory) for Python applications. |
| [`slowapi`](https://github.com/laurentS/slowapi) | Python | Middleware | FastAPI and Starlette integration wrapper built on top of `limits`. |
