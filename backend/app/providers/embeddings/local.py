import asyncio
from collections.abc import Sequence


class LocalEmbeddingProvider:
    def __init__(self, dense_model: str, sparse_model: str, batch_size: int, dense_size: int):
        self.dense_model_name = dense_model
        self.sparse_model_name = sparse_model
        self.batch_size = batch_size
        self._dense_size = dense_size
        self._dense = None
        self._sparse = None
        self._load_lock = asyncio.Lock()

    @property
    def dense_size(self) -> int:
        return self._dense_size

    async def _ensure_loaded(self) -> None:
        if self._dense is not None:
            return
        async with self._load_lock:
            if self._dense is None:
                from fastembed import SparseTextEmbedding, TextEmbedding

                self._dense = await asyncio.to_thread(
                    TextEmbedding, self.dense_model_name
                )
                self._sparse = await asyncio.to_thread(
                    SparseTextEmbedding, self.sparse_model_name
                )

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        await self._ensure_loaded()
        result = await asyncio.to_thread(
            lambda: list(self._dense.embed(list(texts), batch_size=self.batch_size))
        )
        return [vector.tolist() for vector in result]

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]

    async def sparse_documents(self, texts: Sequence[str]) -> list[tuple[list[int], list[float]]]:
        await self._ensure_loaded()
        values = await asyncio.to_thread(
            lambda: list(self._sparse.embed(list(texts), batch_size=self.batch_size))
        )
        return [(item.indices.tolist(), item.values.tolist()) for item in values]

    async def sparse_query(self, text: str) -> tuple[list[int], list[float]]:
        await self._ensure_loaded()
        item = await asyncio.to_thread(lambda: next(iter(self._sparse.query_embed(text))))
        return item.indices.tolist(), item.values.tolist()
