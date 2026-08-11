from datetime import date

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    debug: bool = False

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query cannot be blank")
        return value


class Platforms(BaseModel):
    windows: bool
    mac: bool
    linux: bool


class GameResult(BaseModel):
    app_id: int
    name: str
    release_date: date | None
    about: str
    header_image: str | None
    platforms: Platforms
    rating_percent: float | None
    reviews_count: int
    developers: list[str]
    publishers: list[str]
    genres: list[str]
    categories: list[str]
    tags: list[str]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
