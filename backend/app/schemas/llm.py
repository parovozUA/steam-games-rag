from pydantic import BaseModel, Field


class RerankedItem(BaseModel):
    app_id: int
    score: float = Field(ge=0, le=1)
    match_reason: str | None = Field(None, max_length=240)


class RerankAnswer(BaseModel):
    ranked: list[RerankedItem]
    summary: str = Field(min_length=1, max_length=1000)
