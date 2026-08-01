from datetime import date

from pydantic import BaseModel, Field, model_validator


class SearchFilters(BaseModel):
    operating_systems: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    release_date_from: date | None = None
    release_date_to: date | None = None
    release_year_from: int | None = Field(None, ge=1970, le=2100)
    release_year_to: int | None = Field(None, ge=1970, le=2100)
    genres: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    minimum_rating_percent: float | None = Field(None, ge=0, le=100)
    minimum_reviews_count: int | None = Field(None, ge=0)
    developers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "SearchFilters":
        if self.release_date_from and self.release_date_to:
            if self.release_date_from > self.release_date_to:
                raise ValueError("release_date_from must not exceed release_date_to")
        if self.release_year_from and self.release_year_to:
            if self.release_year_from > self.release_year_to:
                raise ValueError("release_year_from must not exceed release_year_to")
        return self


class QueryUnderstanding(BaseModel):
    detected_language: str = Field(min_length=2, max_length=16)
    rewritten_query_en: str = Field(min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
