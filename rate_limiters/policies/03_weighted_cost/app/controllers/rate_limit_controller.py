"""Controller translating requests into weighted evaluations, headers, and settlements."""

import time
from typing import Any, Callable

from fastapi import HTTPException, Request, Response

from app.config import settings
from app.observability.metrics import LATENCY_SECONDS, record_decision, record_refund
from app.schemas.decision import Decision
from app.services.rate_limiter_service import RateLimiterService


class RateLimitController:
    def __init__(
        self,
        service: RateLimiterService,
        limiter_name: str = "weighted_cost",
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

    def require_cost(self, cost: int = 1) -> Callable[..., Any]:
        async def dependency(request: Request, response: Response) -> None:
            identity = self._resolve_identity(request)
            start = time.perf_counter()

            decision: Decision = await self.service.evaluate(
                identity=identity,
                limit=settings.rl_limit,
                period=settings.rl_period_seconds,
                burst=settings.rl_burst,
                cost=cost,
            )
            duration = time.perf_counter() - start
            LATENCY_SECONDS.labels(limiter=self.limiter_name).observe(duration)

            # Permanent rejection: cost > burst
            if decision.status == "exceeds_burst":
                record_decision(self.limiter_name, outcome="rejected", status="exceeds_burst")
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "cost_exceeds_burst",
                        "message": (
                            f"Requested cost {cost} permanently exceeds burst capacity "
                            f"{decision.limit}. Requests of this size can never be served."
                        ),
                        "cost": cost,
                        "burst": decision.limit,
                    },
                )

            outcome = "allowed" if decision.allowed else "denied"
            record_decision(self.limiter_name, outcome=outcome, status=decision.status)

            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "rule": "weighted_gcra",
                        "retry_after_seconds": int(decision.retry_after),
                        "cost": cost,
                    },
                    headers={
                        "Retry-After": str(int(decision.retry_after)),
                        "RateLimit-Limit": str(decision.limit),
                        "RateLimit-Remaining": str(decision.remaining),
                        "RateLimit-Reset": str(int(decision.reset)),
                    },
                )

            # Allowed response
            response.headers["RateLimit-Limit"] = str(decision.limit)
            response.headers["RateLimit-Remaining"] = str(decision.remaining)
            response.headers["RateLimit-Reset"] = str(int(decision.reset))
            response.headers["X-RateLimit-Cost"] = str(cost)

        return dependency

    async def reserve_and_settle(
        self,
        request: Request,
        estimated_cost: int,
        execute_fn: Callable[[], Any],
    ) -> tuple[Any, int, int]:
        """Reserves estimated cost upfront, executes work, and refunds difference.

        Returns (result, actual_cost, remaining_capacity).
        """
        identity = self._resolve_identity(request)
        decision = await self.service.evaluate(
            identity=identity,
            limit=settings.rl_limit,
            period=settings.rl_period_seconds,
            burst=settings.rl_burst,
            cost=estimated_cost,
        )

        if decision.status == "exceeds_burst":
            record_decision(self.limiter_name, outcome="rejected", status="exceeds_burst")
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "cost_exceeds_burst",
                    "message": f"Estimated cost {estimated_cost} exceeds burst {decision.limit}",
                    "cost": estimated_cost,
                    "burst": decision.limit,
                },
            )

        if not decision.allowed:
            record_decision(self.limiter_name, outcome="denied", status="rate_limited")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "rule": "weighted_gcra",
                    "retry_after_seconds": int(decision.retry_after),
                    "cost": estimated_cost,
                },
                headers={
                    "Retry-After": str(int(decision.retry_after)),
                    "RateLimit-Limit": str(decision.limit),
                    "RateLimit-Remaining": str(decision.remaining),
                    "RateLimit-Reset": str(int(decision.reset)),
                },
            )

        record_decision(self.limiter_name, outcome="allowed", status="reserved")

        # Execute the dynamic work
        result, actual_cost = execute_fn()

        remaining = decision.remaining
        # Settle: refund unused units if actual < estimated
        if actual_cost < estimated_cost:
            refund_amount = estimated_cost - actual_cost
            _, remaining, _ = await self.service.refund(
                identity=identity,
                limit=settings.rl_limit,
                period=settings.rl_period_seconds,
                burst=settings.rl_burst,
                refund_cost=refund_amount,
            )
            record_refund(self.limiter_name, refund_amount)

        return result, actual_cost, remaining
