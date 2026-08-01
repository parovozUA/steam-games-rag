from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.domain.game import Game
from app.domain.search import RetrievalHit
from app.schemas.filters import SearchFilters

T = TypeVar("T", bound=BaseModel)


class EmbeddingProvider(Protocol):
    @property
    def dense_size(self) -> int: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
    async def sparse_documents(
        self, texts: Sequence[str]
    ) -> list[tuple[list[int], list[float]]]: ...
    async def sparse_query(self, text: str) -> tuple[list[int], list[float]]: ...


class VectorStore(Protocol):
    async def wait_until_ready(self, timeout_seconds: float) -> None: ...
    async def ensure_collection(self, dense_size: int) -> None: ...
    async def count(self) -> int: ...
    async def upsert_games(
        self,
        games: Sequence[Game],
        dense: Sequence[Sequence[float]],
        sparse: Sequence[tuple[Sequence[int], Sequence[float]]],
    ) -> None: ...
    async def dense_search(
        self, vector: Sequence[float], filters: SearchFilters, limit: int
    ) -> list[RetrievalHit]: ...
    async def sparse_search(
        self, vector: tuple[Sequence[int], Sequence[float]], filters: SearchFilters, limit: int
    ) -> list[RetrievalHit]: ...
    async def clear(self) -> None: ...
    async def payloads(self, batch_size: int = 256) -> AsyncIterator[dict[str, Any]]: ...


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate_structured(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
        timeout_seconds: float,
    ) -> T: ...
