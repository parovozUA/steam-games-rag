import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.providers.vector_store.qdrant import QdrantVectorStore
from app.rag.fusion import weighted_rrf
from app.schemas.filters import SearchFilters
from app.services.indexing import IndexingCoordinator

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

    async def embed_query(self, text):
        return [1.0, 0.0, 0.0]

    async def sparse_query(self, text):
        return ([101, 202], [2.0, 1.0])


@pytest.mark.asyncio
async def test_real_qdrant_hybrid_index_and_startup(tmp_path):
    url = os.getenv("TEST_QDRANT_URL", "http://localhost:6333")
    store = QdrantVectorStore(url, f"test_steam_{uuid4().hex}")
    collection_created = False
    try:
        await store.wait_until_ready(10)
        await store.ensure_collection(3)
        collection_created = True
        assert await store.count() == 0
        fixture = Path(__file__).parents[1] / "fixtures" / "steam_games.csv"
        coordinator = IndexingCoordinator(
            vector_store=store,
            embeddings=FixedEmbeddings(),
            csv_path=fixture,
            catalog_path=tmp_path / "catalog.json",
            batch_size=2,
            max_retrieval_chars=1000,
        )
        await coordinator.initialize(10)
        await coordinator.wait()
        assert coordinator.status().state == "ready"
        assert await store.count() == 3
        dense = await store.dense_search(
            [1, 0, 0], SearchFilters(operating_systems=["linux"], categories=["Co-op"]), 10
        )
        sparse = await store.sparse_search(
            ([101, 202], [2, 1]), SearchFilters(operating_systems=["linux"]), 10
        )
        assert dense[0].app_id == 10
        assert sparse[0].app_id == 10
        fused = weighted_rrf(
            dense,
            sparse,
            dense_weight=0.65,
            sparse_weight=0.35,
            rrf_k=60,
            limit=10,
        )
        assert fused[0].app_id == 10
        assert fused[0].dense_rank == 1 and fused[0].bm25_rank == 1
        info = await store.client.get_collection(store.collection)
        assert {"genres", "tags", "release_year", "rating_percent"} <= set(info.payload_schema)
    finally:
        if collection_created:
            await store.clear()
        await store.close()
