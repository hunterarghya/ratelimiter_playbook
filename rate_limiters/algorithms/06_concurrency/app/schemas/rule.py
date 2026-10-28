from pydantic import BaseModel, Field


class Rule(BaseModel):
    name: str
    limit: int = Field(gt=0, description="Max concurrent in-flight leases")
    lease_ttl_seconds: int = Field(
        default=30, gt=0, description="Lease expiry duration in seconds"
    )
