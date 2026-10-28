from pydantic import BaseModel, Field


class Decision(BaseModel):
    allowed: bool
    status: str = Field(
        default="allowed",
        description="Outcome: allowed, rate_limited, or exceeds_burst",
    )
    remaining: int = Field(default=0, ge=0)
    retry_after: int = Field(default=0, ge=0)
    reset: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)
    cost: int = Field(default=1, gt=0)
