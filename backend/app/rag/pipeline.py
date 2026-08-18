import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Callable
from uuid import UUID, uuid4

from app.core.config import Settings
from app.observability.tracing import TracingService
from app.prompts.loader import PromptLoader
from app.providers.embeddings.local import LocalEmbeddingProvider
from app.providers.llm.gemini import GeminiAdapter
from app.providers.vector_store.qdrant import QdrantVectorStore
from app.schemas.api import GameResult, Platforms, SearchRequest
from app.schemas.filters import QueryUnderstanding
from app.services.canonicalization import CanonicalCatalog

NO_RESULTS = {
    "en": "No matching games were found.",
    "uk": "Ігор, що відповідають запиту, не знайдено.",
    "de": "Keine passenden Spiele gefunden.",
    "es": "No se encontraron juegos coincidentes.",
    "fr": "Aucun jeu correspondant n’a été trouvé.",
    "pl": "Nie znaleziono pasujących gier.",
}

logger = logging.getLogger(__name__)


class SearchPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        embeddings: LocalEmbeddingProvider,
        vector_store: QdrantVectorStore,
        prompts: PromptLoader,
        gemini: GeminiAdapter,
        catalog: Callable[[], CanonicalCatalog],
        tracer: TracingService | None = None,
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.prompts = prompts
        self.gemini = gemini
        self.catalog = catalog
        self.tracer = tracer or TracingService(settings)

    async def search_stream(
        self, request: SearchRequest, request_id: UUID | None = None
    ) -> AsyncGenerator[str, None]:
        request_id = request_id or uuid4()
        started = time.monotonic()
        timings: dict[str, float] = {}

        with self.tracer.start_trace(
            name="search-steam-games",
            request_id=request_id,
            input_data={"query": request.query, "debug": request.debug},
            tags=["search", "steam-games", self.settings.environment],
            metadata={"environment": self.settings.environment},
        ) as trace_span:
            # 1. Query Understanding
            stage_started = time.monotonic()
            query_prompt = self.prompts.render("query_understanding", query=request.query)
            query_usage: dict[str, int] = {}
            with self.tracer.generation(
                name="understand-query",
                model=self.settings.gemini_model,
                input_data={"system": query_prompt.system, "user": query_prompt.user},
                metadata={"query": request.query},
            ) as query_gen:
                understanding = await self.gemini.generate_structured(
                    system=query_prompt.system,
                    user=query_prompt.user,
                    response_model=QueryUnderstanding,
                    timeout_seconds=self.settings.search_soft_deadline_seconds,
                    on_usage=lambda u: query_usage.update(u),
                )
                query_gen.update(
                    output=understanding.model_dump(mode="json"),
                    usage_details=query_usage or None,
                    metadata={"detected_language": understanding.detected_language},
                )
            understanding.filters = self.catalog().canonicalize(understanding.filters)
            timings["query_understanding_ms"] = round((time.monotonic() - stage_started) * 1000, 2)

            # 2. Embeddings
            stage_started = time.monotonic()
            with self.tracer.span(
                name="generate-embeddings",
                as_type="embedding",
                input_data={"text": understanding.rewritten_query_en},
                metadata={
                    "dense_model": self.settings.dense_embedding_model,
                    "sparse_model": self.settings.sparse_embedding_model,
                },
            ) as emb_span:
                dense_vector, sparse_vector = await asyncio.gather(
                    self.embeddings.embed_query(understanding.rewritten_query_en),
                    self.embeddings.sparse_query(understanding.rewritten_query_en),
                )
                emb_span.update(
                    output={
                        "dense_vector_dim": len(dense_vector),
                        "sparse_indices_count": len(sparse_vector[0]),
                    }
                )

            # 3. Native Qdrant Hybrid Search (RRF)
            stage_started = time.monotonic()
            with self.tracer.span(
                name="hybrid-vector-search",
                as_type="retriever",
                input_data={
                    "filters": understanding.filters.model_dump(mode="json"),
                    "limit": self.settings.result_limit,
                },
                metadata={"collection": self.settings.qdrant_collection},
            ) as ret_span:
                hits = await self.vector_store.hybrid_search(
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector,
                    filters=understanding.filters,
                    limit=self.settings.result_limit,
                )
                ret_span.update(
                    output=[
                        {"app_id": hit.app_id, "score": hit.score, "name": hit.payload.get("name")}
                        for hit in hits
                    ],
                    metadata={"hit_count": len(hits)},
                )
            timings["retrieval_ms"] = round((time.monotonic() - stage_started) * 1000, 2)

            results = [self._game_result(hit) for hit in hits]

            debug = None
            if request.debug:
                debug = {
                    "detected_language": understanding.detected_language,
                    "rewritten_query_en": understanding.rewritten_query_en,
                    "filters": understanding.filters.model_dump(mode="json"),
                    "timings": timings,
                }

            # Yield results first so UI can render cards immediately
            results_payload = {
                "results": [r.model_dump(mode="json") for r in results],
                "debug": debug,
            }
            yield f"event: results\ndata: {json.dumps(results_payload, ensure_ascii=False)}\n\n"

            # 4. Stream Summary
            summary_chunks: list[str] = []
            summary_usage: dict[str, int] = {}
            if results:
                candidate_payload = [self._candidate_for_llm(item) for item in hits]
                rerank_prompt = self.prompts.render(
                    "rerank_and_answer",
                    original_query=request.query,
                    detected_language=understanding.detected_language,
                    filters_json=json.dumps(
                        understanding.filters.model_dump(mode="json"), ensure_ascii=False
                    ),
                    candidates_json=json.dumps(candidate_payload, ensure_ascii=False),
                    result_limit=self.settings.result_limit,
                )

                with self.tracer.generation(
                    name="generate-grounded-summary",
                    model=self.settings.gemini_model,
                    input_data={"system": rerank_prompt.system, "user": rerank_prompt.user},
                    metadata={"candidate_count": len(candidate_payload)},
                ) as summary_gen:
                    async for chunk in self.gemini.stream_chat(
                        system=rerank_prompt.system,
                        user=rerank_prompt.user,
                        timeout_seconds=self.settings.search_hard_deadline_seconds,
                        on_usage=lambda u: summary_usage.update(u),
                    ):
                        summary_chunks.append(chunk)
                        chunk_data = json.dumps(chunk, ensure_ascii=False)
                        yield f"event: summary_chunk\ndata: {chunk_data}\n\n"

                    summary_text = "".join(summary_chunks)
                    summary_gen.update(
                        output=summary_text,
                        usage_details=summary_usage or None,
                    )
            else:
                language = understanding.detected_language.split("-")[0].casefold()
                summary = NO_RESULTS.get(language, NO_RESULTS["en"])
                summary_text = summary
                yield f"event: summary_chunk\ndata: {json.dumps(summary, ensure_ascii=False)}\n\n"

            trace_span.update(
                output={
                    "result_count": len(results),
                    "summary": summary_text,
                    "detected_language": understanding.detected_language,
                }
            )

        total_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            "search_completed",
            extra={
                "request_id": str(request_id),
                "duration": total_ms / 1000,
                "result_count": len(results),
            },
        )
        self.tracer.flush()

    @staticmethod
    def _candidate_for_llm(candidate) -> dict:
        payload = candidate.payload
        return {
            "app_id": candidate.app_id,
            "name": payload.get("name"),
            "release_date": payload.get("release_date"),
            "rating_percent": payload.get("rating_percent"),
            "description": str(payload.get("about", ""))[:600],
        }

    @staticmethod
    def _game_result(candidate) -> GameResult:
        payload = candidate.payload
        return GameResult(
            app_id=candidate.app_id,
            name=payload.get("name") or f"Steam app {candidate.app_id}",
            release_date=payload.get("release_date"),
            about=payload.get("about", ""),
            header_image=payload.get("header_image"),
            platforms=Platforms(
                windows=payload.get("windows", False),
                mac=payload.get("mac", False),
                linux=payload.get("linux", False),
            ),
            rating_percent=payload.get("rating_percent"),
            reviews_count=payload.get("reviews_count", 0),
            developers=payload.get("developers", []),
            publishers=payload.get("publishers", []),
            genres=payload.get("genres", []),
            categories=payload.get("categories", []),
            tags=payload.get("tags", []),
        )
