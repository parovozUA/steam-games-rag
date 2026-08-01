from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


@dataclass(slots=True)
class Game:
    app_id: int
    name: str
    release_date: date | None
    about: str
    header_image: str | None
    windows: bool
    mac: bool
    linux: bool
    positive: int
    negative: int
    rating_percent: float | None
    reviews_count: int
    supported_languages: list[str] = field(default_factory=list)
    developers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    retrieval_text: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "release_date": (
                datetime.combine(self.release_date, datetime.min.time(), tzinfo=UTC)
                .isoformat()
                .replace("+00:00", "Z")
                if self.release_date
                else None
            ),
            "release_year": self.release_date.year if self.release_date else None,
            "about": self.about,
            "header_image": self.header_image,
            "windows": self.windows,
            "mac": self.mac,
            "linux": self.linux,
            "positive": self.positive,
            "negative": self.negative,
            "rating_percent": self.rating_percent,
            "reviews_count": self.reviews_count,
            "supported_languages": self.supported_languages,
            "developers": self.developers,
            "publishers": self.publishers,
            "categories": self.categories,
            "genres": self.genres,
            "tags": self.tags,
            "retrieval_text": self.retrieval_text,
        }
