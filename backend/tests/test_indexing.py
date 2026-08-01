import json
from pathlib import Path

import pytest

from app.services.indexing import IndexingCoordinator

pytestmark = pytest.mark.unit


class FakeEmbeddings:
    dense_size = 2

    async def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def sparse_documents(self, texts):
        return [([1], [1.0]) for _ in texts]


class FakeStore:
    def __init__(self, count):
        self.value = count
        self.upserts = 0

    async def wait_until_ready(self, _wait_seconds):
        pass

    async def ensure_collection(self, size):
        pass

    async def count(self):
        return self.value

    async def upsert_games(self, games, dense, sparse):
        self.upserts += len(games)
        self.value += len(games)

    async def payloads(self, batch_size=256):
        if False:
            yield {}

    async def clear(self):
        self.value = 0


@pytest.mark.asyncio
async def test_existing_collection_skips_indexing(tmp_path):
    store = FakeStore(10)
    coordinator = IndexingCoordinator(
        vector_store=store,
        embeddings=FakeEmbeddings(),
        csv_path=Path("missing"),
        catalog_path=tmp_path / "catalog.json",
        batch_size=2,
        max_retrieval_chars=1000,
    )
    await coordinator.initialize(1)
    assert coordinator.status().state == "ready"
    assert store.upserts == 0


@pytest.mark.asyncio
async def test_empty_collection_starts_initial_indexing(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "steam_games.csv"
    store = FakeStore(0)
    coordinator = IndexingCoordinator(
        vector_store=store,
        embeddings=FakeEmbeddings(),
        csv_path=fixture,
        catalog_path=tmp_path / "catalog.json",
        batch_size=2,
        max_retrieval_chars=1000,
    )
    await coordinator.initialize(1)
    await coordinator.wait()
    assert coordinator.status().state == "ready"
    assert store.upserts == 3


@pytest.mark.asyncio
async def test_missing_csv_exposes_failed_state(tmp_path):
    coordinator = IndexingCoordinator(
        vector_store=FakeStore(0),
        embeddings=FakeEmbeddings(),
        csv_path=tmp_path / "missing.csv",
        catalog_path=tmp_path / "catalog.json",
        batch_size=2,
        max_retrieval_chars=1000,
    )
    await coordinator.initialize(1)
    await coordinator.wait()
    assert coordinator.status().state == "failed"
    assert "CSV not found" in coordinator.status().message


@pytest.mark.asyncio
async def test_nonempty_partial_index_is_not_silently_marked_ready(tmp_path):
    state_path = tmp_path / "indexing_state.json"
    state_path.write_text(
        json.dumps({"state": "indexing", "processed": 5, "failed_rows": 1}),
        encoding="utf-8",
    )
    coordinator = IndexingCoordinator(
        vector_store=FakeStore(5),
        embeddings=FakeEmbeddings(),
        csv_path=Path("missing"),
        catalog_path=tmp_path / "catalog.json",
        state_path=state_path,
        batch_size=2,
        max_retrieval_chars=1000,
    )
    await coordinator.initialize(1)
    assert coordinator.status().state == "failed"
    assert coordinator.status().processed == 5
    assert "manual reindex" in coordinator.status().message
