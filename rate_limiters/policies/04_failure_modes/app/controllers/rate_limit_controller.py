"""Controller translating HTTP requests into failure-mode rate-limit decisions and headers."""

import time
from typing import Any, Callable

from fastapi import HTTPException, Request, Response

from app.observability.metrics import LATENCY_SECONDS
from app.schemas.decision import Decision
from app.services.rate_limiter_service import RateLimiterService


class RateLimitController:
    def __init__(
        self,
        service: RateLimiterService,
        limiter_name: str = "failure_modes",
    ) -> None:
        self.service = service
        self.limiter_name = limiter_name

    def _resolve_identity(self, request: Request) -> str:
        headers = {k.lower(): v for k, v in request.headers.items()}
        if user := headers.get("x-user-id"):
            return f"user:{user}"
        if request.client and request.client.host:
            return f"ip:{request.client.host}"
        return "ip:127.0.0.1"

    def require_mode(self, fail_mode: str = "open") -> Callable[..., Any]:
        """Dependency generator for endpoints specifying a failure mode:

        - 'open': allow traffic if Redis fails, incrementing fail_open metric.
        - 'closed': block with 503 if Redis fails.
        - 'fallback': enforce per-process in-memory token bucket if Redis fails.
        """

        async def dependency(request: Request, response: Response) -> None:
            identity = self._resolve_identity(request)
            start = time.perf_counter()

            decision: Decision = await self.service.evaluate(
                identity=identity,
                fail_mode=fail_mode,
            )
            duration = time.perf_counter() - start
            LATENCY_SECONDS.labels(limiter=self.limiter_name).observe(duration)

            # Failure mode: fail-closed triggers 503 Service Unavailable
            if decision.source == "fail_closed":
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "service_unavailable",
                        "message": "Rate limiter backend unavailable and route is fail-closed",
                    },
                    headers={
                        "Retry-After": "5",
                        "X-RateLimit-Source": "fail_closed",
                    },
                )

            # Set standard rate-limit headers on response
            response.headers["RateLimit-Limit"] = str(decision.limit)
            response.headers["RateLimit-Remaining"] = str(decision.remaining)
            response.headers["RateLimit-Reset"] = str(decision.reset)
            response.headers["X-RateLimit-Source"] = decision.source

            # Denials (either from Redis GCRA or from local fallback)
            if not decision.allowed:
                rule_name = "local_fallback" if decision.source == "local_fallback" else "std"
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "rule": rule_name,
                        "retry_after_seconds": decision.retry_after,
                    },
                    headers={
                        "Retry-After": str(decision.retry_after),
                        "RateLimit-Limit": str(decision.limit),
                        "RateLimit-Remaining": "0",
                        "RateLimit-Reset": str(decision.reset),
                        "X-RateLimit-Source": decision.source,
                    },
                )

        return dependency
