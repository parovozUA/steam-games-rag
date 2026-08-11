import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.providers.vector_store.qdrant import QdrantVectorStore
from app.schemas.filters import SearchFilters
from data_pipeline.csv_games import stream_games

pytestmark = pytest.mark.integration


class FixedEmbeddings:
    dense_size = 3

    async def embed_documents(self, texts):
        return [
            [1.0, 0.0, 0.0] if "space" in text.casefold() else [0.0, 1.0, 0.0] for text in texts
        ]

    async def sparse_documents(self, texts):
        return [
            ([101, 202], [2.0, 1.0]) if "space" in text.casefold() else ([303], [1.0])
            for text in texts
        ]


@pytest.mark.asyncio
async def test_real_qdrant_hybrid_index_and_search():
    url = os.getenv("TEST_QDRANT_URL", "http://localhost:6333")
    store = QdrantVectorStore(url, f"test_steam_{uuid4().hex}")
    collection_created = False
    try:
        await store.wait_until_ready(10)
        await store.ensure_collection(3)
        collection_created = True
        assert await store.count() == 0

        fixture = Path(__file__).parents[1] / "fixtures" / "steam_games.csv"
        games = list(stream_games(fixture, 1000))
        assert len(games) == 3

        emb = FixedEmbeddings()
        texts = [g.retrieval_text for g in games]
        dense = await emb.embed_documents(texts)
        sparse = await emb.sparse_documents(texts)

        await store.upsert_games(games, dense, sparse)
        assert await store.count() == 3

        filters = SearchFilters(operating_systems=["linux"], categories=["Co-op"])
        dense_hits = await store.dense_search([1.0, 0.0, 0.0], filters, 10)
        sparse_hits = await store.sparse_search(([101, 202], [2.0, 1.0]), filters, 10)
        hybrid_hits = await store.hybrid_search(([1.0, 0.0, 0.0]), ([101, 202], [2.0, 1.0]), filters, 10)

        assert len(dense_hits) > 0
        assert dense_hits[0].app_id == 10
        assert len(sparse_hits) > 0
        assert sparse_hits[0].app_id == 10
        assert len(hybrid_hits) > 0
        assert hybrid_hits[0].app_id == 10

        info = await store.client.get_collection(store.collection)
        assert {"genres", "tags", "release_year", "rating_percent"} <= set(info.payload_schema)
    finally:
        if collection_created:
            await store.clear()
        await store.close()

