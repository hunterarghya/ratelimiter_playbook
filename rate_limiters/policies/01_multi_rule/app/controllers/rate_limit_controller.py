"""Controller translating requests into multi-rule evaluations and headers."""

import time
from typing import Any, Callable

from fastapi import HTTPException, Request, Response

from app.observability.metrics import LATENCY_SECONDS, record_decision
from app.schemas.decision import Decision
from app.schemas.rule import Rule
from app.services.identity import resolve_identity
from app.services.rate_limiter_service import RateLimiterService


class RateLimitController:
    def __init__(
        self, service: RateLimiterService, limiter_name: str = "multi_rule"
    ) -> None:
        self.service = service
        self.limiter_name = limiter_name

    def require_rate_limit(
        self, rules: list[Rule], cost: int = 1
    ) -> Callable[..., Any]:
        async def dependency(request: Request, response: Response) -> None:
            headers = {k.lower(): v for k, v in request.headers.items()}
            client_ip = request.client.host if request.client else None
            identity = resolve_identity(headers, client_ip)

            start = time.perf_counter()
            decision: Decision = await self.service.evaluate(identity, rules, cost=cost)
            duration = time.perf_counter() - start

            LATENCY_SECONDS.labels(limiter=self.limiter_name).observe(duration)
            outcome = "allowed" if decision.allowed else "denied"
            rule_label = decision.violated_rule or (rules[0].name if rules else "multi")
            record_decision(self.limiter_name, rule_label, outcome)

            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "rule": decision.violated_rule or rule_label,
                        "retry_after_seconds": int(decision.retry_after),
                    },
                    headers={
                        "Retry-After": str(int(decision.retry_after)),
                        "RateLimit-Limit": str(decision.limit),
                        "RateLimit-Remaining": str(decision.remaining),
                        "RateLimit-Reset": str(int(decision.reset)),
                    },
                )

            # Set headers on allowed response
            response.headers["RateLimit-Limit"] = str(decision.limit)
            response.headers["RateLimit-Remaining"] = str(decision.remaining)
            response.headers["RateLimit-Reset"] = str(int(decision.reset))

        return dependency
