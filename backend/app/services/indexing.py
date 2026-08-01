import asyncio
import itertools
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.providers.protocols import EmbeddingProvider, VectorStore
from app.schemas.api import IndexStatusResponse
from app.services.canonicalization import CanonicalCatalog, CatalogBuilder
from app.services.csv_games import stream_games

logger = logging.getLogger(__name__)


@dataclass
class MutableIndexStatus:
    state: str = "waiting"
    processed: int = 0
    failed_rows: int = 0
    point_count: int = 0
    started_at: float | None = None
    elapsed_seconds: float = 0
    message: str | None = None


class IndexingCoordinator:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embeddings: EmbeddingProvider,
        csv_path: Path,
        catalog_path: Path,
        batch_size: int,
        max_retrieval_chars: int,
        state_path: Path | None = None,
    ):
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.csv_path = csv_path
        self.catalog_path = catalog_path
        self.state_path = state_path or catalog_path.with_name("indexing_state.json")
        self.batch_size = batch_size
        self.max_retrieval_chars = max_retrieval_chars
        self._status = MutableIndexStatus()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.catalog = CanonicalCatalog.load(catalog_path)

    def status(self) -> IndexStatusResponse:
        elapsed = self._status.elapsed_seconds
        if self._status.state == "indexing" and self._status.started_at:
            elapsed = time.monotonic() - self._status.started_at
        return IndexStatusResponse(
            state=self._status.state,
            processed=self._status.processed,
            failed_rows=self._status.failed_rows,
            point_count=self._status.point_count,
            elapsed_seconds=round(elapsed, 3),
            message=self._status.message,
        )

    async def initialize(self, qdrant_timeout: float) -> None:
        await self.vector_store.wait_until_ready(qdrant_timeout)
        await self.vector_store.ensure_collection(self.embeddings.dense_size)
        count = await self.vector_store.count()
        self._status.point_count = count
        if count:
            persisted = self._load_persisted_state()
            if persisted and persisted.get("state") in {"indexing", "failed"}:
                self._status.state = "failed"
                self._status.processed = int(persisted.get("processed", count))
                self._status.failed_rows = int(persisted.get("failed_rows", 0))
                self._status.elapsed_seconds = float(persisted.get("elapsed_seconds", 0))
                self._status.message = (
                    "A partial or failed ingestion was detected; run the manual reindex command"
                )
                return
            if not self.catalog_path.exists():
                builder = CatalogBuilder()
                async for payload in self.vector_store.payloads():
                    builder.add_payload(payload)
                self.catalog = builder.build()
                self.catalog.save(self.catalog_path)
            self._status.state = "ready"
            self._status.message = "Existing index is ready"
        else:
            self.start()

    def start(self) -> bool:
        if self._task and not self._task.done():
            return False
        self._task = asyncio.create_task(self._run(), name="initial-steam-indexing")
        return True

    async def wait(self) -> None:
        if self._task:
            await self._task

    async def reindex(self) -> bool:
        if self._task and not self._task.done():
            return False
        await self.vector_store.clear()
        await self.vector_store.ensure_collection(self.embeddings.dense_size)
        self.catalog = CanonicalCatalog()
        return self.start()

    async def _run(self) -> None:
        async with self._lock:
            self._status = MutableIndexStatus(state="indexing", started_at=time.monotonic())
            self._persist_state()
            if not self.csv_path.is_file():
                self._status.state = "failed"
                self._status.elapsed_seconds = time.monotonic() - self._status.started_at
                self._status.message = f"CSV not found or unreadable: {self.csv_path}"
                self._persist_state()
                return
            builder = CatalogBuilder()
            try:

                def record_failure(line_number: int, reason: str) -> None:
                    self._status.failed_rows += 1
                    logger.warning(
                        "indexing_row_skipped",
                        extra={
                            "pipeline_stage": "indexing",
                            "line_number": line_number,
                            "failure_category": "invalid_csv_row",
                            "reason": reason[:200],
                        },
                    )

                iterator = stream_games(
                    self.csv_path, self.max_retrieval_chars, on_failure=record_failure
                )
                while True:
                    batch = await asyncio.to_thread(
                        lambda: list(itertools.islice(iterator, self.batch_size))
                    )
                    if not batch:
                        break
                    texts = [game.retrieval_text for game in batch]
                    dense, sparse = await asyncio.gather(
                        self.embeddings.embed_documents(texts),
                        self.embeddings.sparse_documents(texts),
                    )
                    await self.vector_store.upsert_games(batch, dense, sparse)
                    for game in batch:
                        builder.add_payload(game.payload())
                    self._status.processed += len(batch)
                    self._status.point_count = self._status.processed
                    await asyncio.to_thread(self._persist_state)
                    logger.info(
                        "indexing_progress",
                        extra={
                            "pipeline_stage": "indexing",
                            "processed": self._status.processed,
                            "failed_rows": self._status.failed_rows,
                            "duration": time.monotonic() - self._status.started_at,
                        },
                    )
                self.catalog = builder.build()
                self.catalog.save(self.catalog_path)
                self._status.elapsed_seconds = time.monotonic() - self._status.started_at
                self._status.state = "ready"
                self._status.point_count = await self.vector_store.count()
                self._status.message = f"Indexed {self._status.point_count} games"
                self._persist_state()
            except Exception as exc:
                logger.exception("indexing_failed", extra={"pipeline_stage": "indexing"})
                self._status.elapsed_seconds = time.monotonic() - self._status.started_at
                self._status.state = "failed"
                self._status.message = f"Indexing failed: {type(exc).__name__}: {exc}"
                self._persist_state()

    def _load_persisted_state(self) -> dict | None:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"state": "failed"}

    def _persist_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "state": self._status.state,
                    "processed": self._status.processed,
                    "failed_rows": self._status.failed_rows,
                    "point_count": self._status.point_count,
                    "elapsed_seconds": self._status.elapsed_seconds,
                    "message": self._status.message,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
