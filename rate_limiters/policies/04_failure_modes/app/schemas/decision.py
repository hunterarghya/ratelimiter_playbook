from pydantic import BaseModel, Field


class Decision(BaseModel):
    allowed: bool
    remaining: int = Field(default=0, ge=0)
    retry_after: int = Field(default=0, ge=0)
    reset: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)
    source: str = Field(
        default="redis",
        description="Decision source: redis, fail_open, fail_closed, local_fallback",
    )
