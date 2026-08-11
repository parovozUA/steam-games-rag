import asyncio
import itertools
import logging
import sys
import time

from app.core.config import get_settings
from app.providers.embeddings.local import LocalEmbeddingProvider
from app.providers.vector_store.qdrant import QdrantVectorStore
from app.services.canonicalization import CatalogBuilder
from data_pipeline.csv_games import stream_games

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    settings = get_settings()
    csv_path = settings.steam_csv_path
    catalog_path = settings.canonical_catalog_path
    batch_size = settings.ingestion_batch_size

    if not csv_path.exists():
        logger.error(f"CSV not found at {csv_path}")
        return

    embeddings = LocalEmbeddingProvider(
        settings.dense_embedding_model,
        settings.sparse_embedding_model,
        settings.embedding_batch_size,
        settings.dense_vector_size,
    )
    vector_store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection)
    
    await vector_store.wait_until_ready(10.0)
    
    force = "--force" in sys.argv
    try:
        count = await vector_store.count()
        if count > 0 and not force:
            logger.info(f"Index already contains {count} games. Skipping ingestion.")
            logger.info(
                "If you want to reindex, run with --force flag: "
                "python -m data_pipeline.ingest --force"
            )
            await vector_store.close()
            return
    except Exception:
        pass

    logger.info("Clearing vector store and ensuring collection exists...")
    await vector_store.clear()
    await vector_store.ensure_collection(embeddings.dense_size)

    builder = CatalogBuilder()
    processed = 0
    started_at = time.monotonic()

    def record_failure(line_number: int, reason: str) -> None:
        logger.warning(f"Row {line_number} skipped: {reason}")

    iterator = stream_games(csv_path, settings.retrieval_text_max_chars, on_failure=record_failure)
    
    while True:
        batch = await asyncio.to_thread(lambda: list(itertools.islice(iterator, batch_size)))
        if not batch:
            break
        texts = [game.retrieval_text for game in batch]
        dense, sparse = await asyncio.gather(
            embeddings.embed_documents(texts),
            embeddings.sparse_documents(texts),
        )
        await vector_store.upsert_games(batch, dense, sparse)
        for game in batch:
            builder.add_payload(game.payload())
        processed += len(batch)
        logger.info(f"Indexed {processed} games. Elapsed: {time.monotonic() - started_at:.1f}s")

    catalog = builder.build()
    catalog.save(catalog_path)
    logger.info(f"Finished indexing {processed} games. Catalog saved.")
    await vector_store.close()

if __name__ == "__main__":
    asyncio.run(main())
