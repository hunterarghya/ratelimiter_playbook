from pydantic import BaseModel, Field


class Rule(BaseModel):
    name: str
    limit: int = Field(gt=0, description="Max allowed requests per period")
    period: int = Field(gt=0, description="Window period in seconds")
    burst: int = Field(default=0, description="Max instantaneous capacity")

    def model_post_init(self, __context: object) -> None:
        if self.burst <= 0:
            self.burst = self.limit
