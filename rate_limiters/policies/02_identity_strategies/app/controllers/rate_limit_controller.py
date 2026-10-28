"""Controller translating requests into identity-targeted evaluations and headers."""

import time
from typing import Any, Callable

from fastapi import HTTPException, Request, Response

from app.config import settings
from app.observability.metrics import LATENCY_SECONDS, record_decision
from app.schemas.decision import Decision
from app.schemas.rule import Rule
from app.services.identity import (
    resolve_api_key_identity,
    resolve_composite_ip_user_identity,
    resolve_endpoint_identity,
    resolve_global_identity,
    resolve_ip_identity,
    resolve_tenant_identity,
    resolve_user_identity,
)
from app.services.rate_limiter_service import RateLimiterService


class RateLimitController:
    def __init__(
        self, service: RateLimiterService, limiter_name: str = "identity_strategies"
    ) -> None:
        self.service = service
        self.limiter_name = limiter_name

    def require_targets(
        self, target_resolver: Callable[[Request], list[tuple[str, Rule]]], cost: int = 1
    ) -> Callable[..., Any]:
        async def dependency(request: Request, response: Response) -> None:
            targets = target_resolver(request)
            start = time.perf_counter()
            decision: Decision = await self.service.evaluate(targets, cost=cost)
            duration = time.perf_counter() - start

            LATENCY_SECONDS.labels(limiter=self.limiter_name).observe(duration)
            outcome = "allowed" if decision.allowed else "denied"
            rule_label = decision.violated_rule or (targets[0][1].name if targets else "id")
            record_decision(self.limiter_name, rule_label, outcome)

            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "rule": decision.violated_rule or rule_label,
                        "retry_after_seconds": int(decision.retry_after),
                        "identity": decision.resolved_identity,
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
            if decision.resolved_identity:
                response.headers["X-RateLimit-Identity"] = decision.resolved_identity

        return dependency

    def require_ip_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            client_ip = req.client.host if req.client else None
            identity = resolve_ip_identity(headers, client_ip, settings.rl_trusted_proxy_count)
            return [(identity, rule)]

        return self.require_targets(resolver)

    def require_user_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            identity = resolve_user_identity(headers) or "user:anonymous"
            return [(identity, rule)]

        return self.require_targets(resolver)

    def require_api_key_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            identity = resolve_api_key_identity(headers) or "key:missing"
            return [(identity, rule)]

        return self.require_targets(resolver)

    def require_tenant_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            identity = resolve_tenant_identity(headers) or "tenant:default"
            return [(identity, rule)]

        return self.require_targets(resolver)

    def require_endpoint_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            client_ip = req.client.host if req.client else None
            identity = resolve_endpoint_identity(
                headers, req.method, req.url.path, client_ip, settings.rl_trusted_proxy_count
            )
            return [(identity, rule)]

        return self.require_targets(resolver)

    def require_global_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(_: Request) -> list[tuple[str, Rule]]:
            return [(resolve_global_identity(), rule)]

        return self.require_targets(resolver)

    def require_composite_ip_user_limit(self, rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            client_ip = req.client.host if req.client else None
            identity = resolve_composite_ip_user_identity(
                headers, client_ip, settings.rl_trusted_proxy_count
            )
            return [(identity, rule)]

        return self.require_targets(resolver)

    def require_transition_limit(self, ip_rule: Rule, user_rule: Rule) -> Callable[..., Any]:
        def resolver(req: Request) -> list[tuple[str, Rule]]:
            headers = {k.lower(): v for k, v in req.headers.items()}
            client_ip = req.client.host if req.client else None
            ip_id = resolve_ip_identity(headers, client_ip, settings.rl_trusted_proxy_count)
            user_id = resolve_user_identity(headers)

            targets = [(ip_id, ip_rule)]
            if user_id:
                targets.append((user_id, user_rule))
            return targets

        return self.require_targets(resolver)
