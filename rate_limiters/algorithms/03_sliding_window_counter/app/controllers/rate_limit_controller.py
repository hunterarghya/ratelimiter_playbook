"""Controller translating HTTP requests into rate limiter evaluations and response headers."""

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
        self, service: RateLimiterService, limiter_name: str = "sliding_counter"
    ) -> None:
        self.service = service
        self.limiter_name = limiter_name

    def require_rate_limit(self, rule: Rule) -> Callable[..., Any]:
        async def dependency(request: Request, response: Response) -> None:
            headers = {k.lower(): v for k, v in request.headers.items()}
            client_ip = request.client.host if request.client else None
            identity = resolve_identity(headers, client_ip)

            start = time.perf_counter()
            decision: Decision = await self.service.evaluate(identity, rule)
            duration = time.perf_counter() - start

            LATENCY_SECONDS.labels(limiter=self.limiter_name).observe(duration)
            outcome = "allowed" if decision.allowed else "denied"
            record_decision(self.limiter_name, rule.name, outcome)

            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "rule": decision.violated_rule or rule.name,
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
