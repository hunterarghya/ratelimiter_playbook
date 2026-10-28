"""Controller applying Enforce, Shadow, or Allowlist rate limiting to incoming HTTP requests."""

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
        limiter_name: str = "shadow_mode",
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

    def require_rate_limit(self, mode: str | None = None) -> Callable[..., Any]:
        """Dependency generator for endpoints:

        - mode=None: uses dynamic global mode (settings.rl_mode or admin toggled)
        - mode='enforce': explicitly strictly enforced
        - mode='shadow': explicitly shadowed (always returns 200, metrics would-block)
        """

        async def dependency(request: Request, response: Response) -> None:
            identity = self._resolve_identity(request)
            start = time.perf_counter()

            decision: Decision = await self.service.evaluate(
                identity=identity,
                mode=mode,
            )
            duration = time.perf_counter() - start
            LATENCY_SECONDS.labels(limiter=self.limiter_name).observe(duration)

            # Set response headers
            response.headers["RateLimit-Limit"] = str(decision.limit)
            response.headers["RateLimit-Remaining"] = str(decision.remaining)
            response.headers["RateLimit-Reset"] = str(decision.reset)
            response.headers["X-RateLimit-Mode"] = decision.mode
            response.headers["X-RateLimit-Action"] = decision.action

            if decision.would_block:
                response.headers["X-RateLimit-Would-Block"] = "true"
                response.headers["X-RateLimit-Retry-After"] = str(decision.retry_after)

            # If Enforce mode rejected the request -> 429 Too Many Requests
            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "rule": "std",
                        "retry_after_seconds": decision.retry_after,
                    },
                    headers={
                        "Retry-After": str(decision.retry_after),
                        "RateLimit-Limit": str(decision.limit),
                        "RateLimit-Remaining": "0",
                        "RateLimit-Reset": str(decision.reset),
                        "X-RateLimit-Mode": decision.mode,
                        "X-RateLimit-Action": decision.action,
                    },
                )

        return dependency
