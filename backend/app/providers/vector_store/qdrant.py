import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, time
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.domain.game import Game
from app.domain.search import RetrievalHit
from app.schemas.filters import SearchFilters


def build_qdrant_filter(filters: SearchFilters) -> models.Filter | None:
    must: list[models.FieldCondition] = []
    for os_name in filters.operating_systems:
        must.append(models.FieldCondition(key=os_name, match=models.MatchValue(value=True)))
    for field in (
        "supported_languages",
        "genres",
        "categories",
        "tags",
        "developers",
        "publishers",
    ):
        values = getattr(filters, field)
        if values:
            must.append(models.FieldCondition(key=field, match=models.MatchAny(any=values)))
    if filters.release_year_from is not None or filters.release_year_to is not None:
        must.append(
            models.FieldCondition(
                key="release_year",
                range=models.Range(gte=filters.release_year_from, lte=filters.release_year_to),
            )
        )
    if filters.release_date_from is not None or filters.release_date_to is not None:
        gte = (
            datetime.combine(filters.release_date_from, time.min, tzinfo=UTC)
            if filters.release_date_from
            else None
        )
        lte = (
            datetime.combine(filters.release_date_to, time.max, tzinfo=UTC)
            if filters.release_date_to
            else None
        )
        must.append(
            models.FieldCondition(key="release_date", range=models.DatetimeRange(gte=gte, lte=lte))
        )
    if filters.minimum_rating_percent is not None:
        must.append(
            models.FieldCondition(
                key="rating_percent", range=models.Range(gte=filters.minimum_rating_percent)
            )
        )
    if filters.minimum_reviews_count is not None:
        must.append(
            models.FieldCondition(
                key="reviews_count", range=models.Range(gte=filters.minimum_reviews_count)
            )
        )
    return models.Filter(must=must) if must else None


class QdrantVectorStore:
    def __init__(self, url: str, collection: str):
        self.client = AsyncQdrantClient(url=url, timeout=10)
        self.collection = collection

    async def wait_until_ready(self, timeout_seconds: float) -> None:
        async with asyncio.timeout(timeout_seconds):
            while True:
                try:
                    await self.client.get_collections()
                    return
                except Exception:
                    await asyncio.sleep(0.5)

    async def ensure_collection(self, dense_size: int) -> None:
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    "dense": models.VectorParams(size=dense_size, distance=models.Distance.COSINE)
                },
                sparse_vectors_config={
                    "bm25": models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                        index=models.SparseIndexParams(on_disk=True),
                    )
                },
                on_disk_payload=True,
            )
        indexes = {
            "app_id": models.PayloadSchemaType.INTEGER,
            "release_date": models.PayloadSchemaType.DATETIME,
            "release_year": models.PayloadSchemaType.INTEGER,
            "rating_percent": models.PayloadSchemaType.FLOAT,
            "reviews_count": models.PayloadSchemaType.INTEGER,
            "windows": models.PayloadSchemaType.BOOL,
            "mac": models.PayloadSchemaType.BOOL,
            "linux": models.PayloadSchemaType.BOOL,
            "supported_languages": models.PayloadSchemaType.KEYWORD,
            "developers": models.PayloadSchemaType.KEYWORD,
            "publishers": models.PayloadSchemaType.KEYWORD,
            "categories": models.PayloadSchemaType.KEYWORD,
            "genres": models.PayloadSchemaType.KEYWORD,
            "tags": models.PayloadSchemaType.KEYWORD,
        }
        info = await self.client.get_collection(self.collection)
        existing = set((info.payload_schema or {}).keys())
        for field, schema in indexes.items():
            if field not in existing:
                await self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=schema,
                    wait=True,
                )

    async def count(self) -> int:
        result = await self.client.count(self.collection, exact=True)
        return result.count

    async def upsert_games(
        self,
        games: Sequence[Game],
        dense: Sequence[Sequence[float]],
        sparse: Sequence[tuple[Sequence[int], Sequence[float]]],
    ) -> None:
        points = [
            models.PointStruct(
                id=game.app_id,
                vector={
                    "dense": list(dense_vector),
                    "bm25": models.SparseVector(
                        indices=list(sparse_vector[0]), values=list(sparse_vector[1])
                    ),
                },
                payload=game.payload(),
            )
            for game, dense_vector, sparse_vector in zip(games, dense, sparse, strict=True)
        ]
        await self.client.upsert(self.collection, points=points, wait=True)

    async def hybrid_search(
        self,
        dense_vector: Sequence[float],
        sparse_vector: tuple[Sequence[int], Sequence[float]],
        filters: SearchFilters,
        limit: int,
    ) -> list[RetrievalHit]:
        qdrant_filter = build_qdrant_filter(filters)
        prefetch = [
            models.Prefetch(
                query=list(dense_vector),
                using="dense",
                limit=limit,
                filter=qdrant_filter,
            ),
            models.Prefetch(
                query=models.SparseVector(indices=list(sparse_vector[0]), values=list(sparse_vector[1])),
                using="bm25",
                limit=limit,
                filter=qdrant_filter,
            ),
        ]
        result = await self.client.query_points(
            collection_name=self.collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [
            RetrievalHit(int(point.id), dict(point.payload or {}), float(point.score))
            for point in result.points
        ]

    async def clear(self) -> None:
        if await self.client.collection_exists(self.collection):
            await self.client.delete_collection(self.collection)

    async def payloads(self, batch_size: int = 256) -> AsyncIterator[dict[str, Any]]:
        offset = None
        while True:
            points, offset = await self.client.scroll(
                self.collection,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                yield dict(point.payload or {})
            if offset is None:
                break

    async def close(self) -> None:
        await self.client.close()
