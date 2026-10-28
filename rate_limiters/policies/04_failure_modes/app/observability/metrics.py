from prometheus_client import Counter, Histogram

DECISIONS = Counter(
    "rl_decisions_total",
    "Rate limiter decisions",
    ["limiter", "outcome", "status"],
)

FAIL_OPEN = Counter(
    "rl_fail_open_total",
    "Rate limiter fail-open total count",
    ["limiter"],
)

LATENCY_SECONDS = Histogram(
    "rl_latency_seconds",
    "Time spent making rate limiter decision in seconds",
    ["limiter"],
)


def record_decision(limiter: str, outcome: str, status: str = "allowed") -> None:
    DECISIONS.labels(limiter=limiter, outcome=outcome, status=status).inc()
    if status == "fail_open":
        FAIL_OPEN.labels(limiter=limiter).inc()
