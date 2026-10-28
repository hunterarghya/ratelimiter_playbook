from prometheus_client import Counter, Histogram

DECISIONS = Counter(
    "rl_decisions_total",
    "Rate limiter decisions",
    ["limiter", "outcome", "status"],
)

LATENCY_SECONDS = Histogram(
    "rl_latency_seconds",
    "Time spent making rate limiter decision in seconds",
    ["limiter"],
)

REFUNDS = Counter(
    "rl_refunds_total",
    "Total units refunded to rate limiters",
    ["limiter"],
)


def record_decision(limiter: str, outcome: str, status: str = "allowed") -> None:
    DECISIONS.labels(limiter=limiter, outcome=outcome, status=status).inc()


def record_refund(limiter: str, units: int) -> None:
    REFUNDS.labels(limiter=limiter).inc(units)
