from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Steam Games RAG"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,https://test.constantine.software"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_rpm: int = Field(30, ge=1)

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "steam_games"
    steam_csv_path: Path = Path("data/steam_games.csv")
    prompt_registry_path: Path = Path("../prompts/registry.yaml")
    canonical_catalog_path: Path = Path("data/canonical_values.json")

    dense_embedding_model: str = "intfloat/multilingual-e5-large"
    sparse_embedding_model: str = "Qdrant/bm25"
    dense_vector_size: int = Field(1024, ge=1)
    embedding_batch_size: int = Field(16, ge=1, le=256)
    ingestion_batch_size: int = Field(64, ge=1, le=1024)
    retrieval_text_max_chars: int = Field(3000, ge=256)

    result_limit: int = Field(10, ge=1, le=50)
    search_soft_deadline_seconds: float = Field(10, gt=0)
    search_hard_deadline_seconds: float = Field(15, gt=0)

    @model_validator(mode="after")
    def validate_related_values(self) -> "Settings":
        if self.search_soft_deadline_seconds > self.search_hard_deadline_seconds:
            raise ValueError("SEARCH_SOFT_DEADLINE_SECONDS cannot exceed hard deadline")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
