from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    prompt: str = Field(description="Input text prompt for mock LLM generation")
    estimated_tokens: int = Field(
        default=4,
        gt=0,
        description="Estimated token count to reserve upfront",
    )


class LLMResponse(BaseModel):
    prompt: str
    completion: str
    estimated_tokens: int
    actual_tokens: int
    refunded_tokens: int
    remaining_tokens: int
