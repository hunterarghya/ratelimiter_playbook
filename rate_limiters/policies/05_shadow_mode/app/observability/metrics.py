from prometheus_client import Counter, Histogram

DECISIONS = Counter(
    "rl_decisions_total",
    "Rate limiter decisions",
    ["limiter", "outcome", "status"],
)

SHADOW_DENIED = Counter(
    "rl_shadow_denied_total",
    "Requests that would have been blocked under enforcement",
    ["limiter", "rule"],
)

BYPASSED = Counter(
    "rl_bypassed_total",
    "Requests that bypassed rate limiting via allowlist",
    ["limiter"],
)

LATENCY_SECONDS = Histogram(
    "rl_latency_seconds",
    "Time spent making rate limiter decision in seconds",
    ["limiter"],
)


def record_decision(limiter: str, outcome: str, status: str = "allowed") -> None:
    DECISIONS.labels(limiter=limiter, outcome=outcome, status=status).inc()
    if outcome == "shadow_denied":
        SHADOW_DENIED.labels(limiter=limiter, rule="std").inc()
    elif outcome == "bypassed":
        BYPASSED.labels(limiter=limiter).inc()
