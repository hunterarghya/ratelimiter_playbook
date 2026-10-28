from pydantic import BaseModel


class Decision(BaseModel):
    allowed: bool
    retry_after: int | float
    remaining: int
    reset: int | float
    violated_rule: str | None = None
    limit: int = 0
