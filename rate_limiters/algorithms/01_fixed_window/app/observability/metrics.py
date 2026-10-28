from prometheus_client import Counter, Histogram

DECISIONS_TOTAL = Counter(
    "rl_decisions_total",
    "Total number of rate limiter decisions",
    ["limiter", "rule", "outcome"],
)

LATENCY_SECONDS = Histogram(
    "rl_latency_seconds",
    "Latency of rate limiter evaluation in seconds",
    ["limiter"],
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)


def record_decision(limiter: str, rule: str, outcome: str) -> None:
    DECISIONS_TOTAL.labels(limiter=limiter, rule=rule, outcome=outcome).inc()
