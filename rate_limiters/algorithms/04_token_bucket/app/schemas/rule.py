from pydantic import BaseModel, Field


class Rule(BaseModel):
    name: str
    limit: int = Field(gt=0, description="Sustained rate limit (tokens per period)")
    period: int = Field(gt=0, description="Window duration in seconds")
    burst: int = Field(default=0, description="Bucket capacity (max burst size)")
    cost: int = Field(default=1, gt=0, description="Token cost for this request")

    def model_post_init(self, __context: object) -> None:
        if self.burst <= 0:
            self.burst = self.limit
