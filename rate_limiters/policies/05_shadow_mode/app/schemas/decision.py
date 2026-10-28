from pydantic import BaseModel, Field


class Decision(BaseModel):
    allowed: bool
    action: str = Field(
        default="allowed",
        description="Outcome action: allowed, denied, shadow_denied, bypassed",
    )
    mode: str = Field(
        default="shadow",
        description="Operating mode: enforce, shadow, allowlist",
    )
    remaining: int = Field(default=0, ge=0)
    retry_after: int = Field(default=0, ge=0)
    reset: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)
    would_block: bool = Field(
        default=False,
        description="Whether shadow mode observed a rate limit violation",
    )
    identity: str = Field(default="")
