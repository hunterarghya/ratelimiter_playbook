"""Demo routes for weighted cost rate limiter."""

import time

from fastapi import APIRouter, Depends, Request

from app.controllers.rate_limit_controller import RateLimitController
from app.schemas.request import LLMRequest, LLMResponse

router = APIRouter(prefix="/demo", tags=["demo"])


def create_demo_router(controller: RateLimitController) -> APIRouter:
    @router.get("/limited", dependencies=[Depends(controller.require_cost(1))])
    async def limited_endpoint() -> dict[str, str | float]:
        return {"message": "weighted default request allowed", "timestamp": time.time()}

    @router.get("/query", dependencies=[Depends(controller.require_cost(1))])
    async def query_endpoint() -> dict[str, str | float | int]:
        return {"message": "query allowed", "cost": 1, "timestamp": time.time()}

    @router.get("/report", dependencies=[Depends(controller.require_cost(2))])
    async def report_endpoint() -> dict[str, str | float | int]:
        return {"message": "report generation allowed", "cost": 2, "timestamp": time.time()}

    @router.get("/export", dependencies=[Depends(controller.require_cost(4))])
    async def export_endpoint() -> dict[str, str | float | int]:
        return {"message": "export allowed", "cost": 4, "timestamp": time.time()}

    @router.get("/oversized", dependencies=[Depends(controller.require_cost(100))])
    async def oversized_endpoint() -> dict[str, str]:
        return {"message": "unreachable: cost 100 exceeds burst capacity"}

    @router.post("/llm", response_model=LLMResponse)
    async def mock_llm_endpoint(req: LLMRequest, request: Request) -> LLMResponse:
        def mock_generate() -> tuple[str, int]:
            # Mock LLM generation: actual token cost is prompt words + fixed output tokens
            output_tokens = 5
            prompt_words = len(req.prompt.split())
            actual = prompt_words + output_tokens
            completion = f"Mock LLM completion for: '{req.prompt}' (synthesized {actual} tokens)"
            return completion, actual

        completion, actual_tokens, remaining = await controller.reserve_and_settle(
            request=request,
            estimated_cost=req.estimated_tokens,
            execute_fn=mock_generate,
        )

        refunded = max(0, req.estimated_tokens - actual_tokens)
        return LLMResponse(
            prompt=req.prompt,
            completion=completion,
            estimated_tokens=req.estimated_tokens,
            actual_tokens=actual_tokens,
            refunded_tokens=refunded,
            remaining_tokens=remaining,
        )

    return router
