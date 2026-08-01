import asyncio
import json
import logging
import time
from collections.abc import Callable
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.deadline import Deadline
from app.core.errors import IndexNotReadyError
from app.domain.search import Candidate
from app.prompts.loader import PromptLoader
from app.providers.protocols import EmbeddingProvider, LLMProvider, VectorStore
from app.rag.fusion import weighted_rrf
from app.rag.rerank import apply_rerank
from app.schemas.api import GameResult, Platforms, SearchRequest, SearchResponse
from app.schemas.filters import QueryUnderstanding
from app.schemas.llm import RerankAnswer
from app.services.canonicalization import CanonicalCatalog
from app.services.indexing import IndexingCoordinator
from app.services.llm_routing import SearchLLMSession

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
        indexing: IndexingCoordinator,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        prompts: PromptLoader,
        gemini: LLMProvider,
        openai: LLMProvider,
        catalog: Callable[[], CanonicalCatalog],
    ):
        self.settings = settings
        self.indexing = indexing
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.prompts = prompts
        self.gemini = gemini
        self.openai = openai
        self.catalog = catalog

    async def search(
        self, request: SearchRequest, request_id: UUID | None = None
    ) -> SearchResponse:
        request_id = request_id or uuid4()
        started = time.monotonic()
        if self.indexing.status().state != "ready":
            status = self.indexing.status()
            raise IndexNotReadyError(
                status.message or f"Index state: {status.state}", str(request_id)
            )
        deadline = Deadline.after(self.settings.search_hard_deadline_seconds)
        session = SearchLLMSession(
            self.gemini,
            self.openai,
            deadline,
            str(request_id),
            soft_deadline=Deadline.after(self.settings.search_soft_deadline_seconds),
        )
        timings: dict[str, float] = {}

        stage_started = time.monotonic()
        query_prompt = self.prompts.render("query_understanding", query=request.query)
        understanding = await session.call(
            "query_understanding",
            system=query_prompt.system,
            user=query_prompt.user,
            response_model=QueryUnderstanding,
        )
        understanding.filters = self.catalog().canonicalize(understanding.filters)
        timings["query_understanding_ms"] = round((time.monotonic() - stage_started) * 1000, 2)

        stage_started = time.monotonic()
        dense_vector, sparse_vector = await deadline.run(
            asyncio.gather(
                self.embeddings.embed_query(understanding.rewritten_query_en),
                self.embeddings.sparse_query(understanding.rewritten_query_en),
            )
        )
        dense_hits, sparse_hits = await deadline.run(
            asyncio.gather(
                self.vector_store.dense_search(
                    dense_vector, understanding.filters, self.settings.dense_top_k
                ),
                self.vector_store.sparse_search(
                    sparse_vector, understanding.filters, self.settings.sparse_top_k
                ),
            )
        )
        candidates = weighted_rrf(
            dense_hits,
            sparse_hits,
            dense_weight=self.settings.dense_weight,
            sparse_weight=self.settings.bm25_weight,
            rrf_k=self.settings.rrf_k,
            limit=self.settings.fusion_top_k,
        )[: self.settings.rerank_candidates]
        timings["retrieval_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
        logger.info(
            "retrieval_completed",
            extra={
                "request_id": str(request_id),
                "pipeline_stage": "retrieval",
                "duration": timings["retrieval_ms"] / 1000,
                "dense_candidates": len(dense_hits),
                "bm25_candidates": len(sparse_hits),
                "fusion_candidates": len(candidates),
            },
        )

        rerank_prompt = None
        if candidates:
            candidate_payload = [self._candidate_for_llm(item) for item in candidates]
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
            stage_started = time.monotonic()
            rerank_output = await session.call(
                "rerank_and_answer",
                system=rerank_prompt.system,
                user=rerank_prompt.user,
                response_model=RerankAnswer,
            )
            selected = apply_rerank(candidates, rerank_output, self.settings.result_limit)
            summary = rerank_output.summary
            timings["rerank_and_answer_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
        else:
            selected = []
            language = understanding.detected_language.split("-")[0].casefold()
            summary = NO_RESULTS.get(language, NO_RESULTS["en"])

        results = [self._game_result(item) for item in selected]
        total_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            "search_completed",
            extra={
                "request_id": str(request_id),
                "pipeline_stage": "complete",
                "duration": total_ms / 1000,
                "candidate_count": len(candidates),
                "result_count": len(results),
                "gemini_attempts": session.gemini_attempts,
                "fallback_activated": session.fallback_activated,
            },
        )
        debug = None
        if request.debug:
            debug = {
                "detected_language": understanding.detected_language,
                "rewritten_query_en": understanding.rewritten_query_en,
                "filters": understanding.filters.model_dump(mode="json"),
                "prompts": {
                    "query_understanding": {
                        "id": query_prompt.prompt_id,
                        "version": query_prompt.version,
                    },
                    **(
                        {
                            "rerank_and_answer": {
                                "id": rerank_prompt.prompt_id,
                                "version": rerank_prompt.version,
                            }
                        }
                        if rerank_prompt
                        else {}
                    ),
                },
                "providers": {
                    name: {
                        "provider": diag.provider,
                        "model": diag.model,
                    }
                    for name, diag in session.stages.items()
                },
                "timings": {
                    **timings,
                    **{
                        f"{name}_provider_ms": diag.duration_ms
                        for name, diag in session.stages.items()
                    },
                    "total_ms": total_ms,
                },
                "gemini_attempts": session.gemini_attempts,
                "fallback_activated": session.fallback_activated,
                "retrieval": [self._diagnostic(item) for item in selected],
            }
        return SearchResponse(
            request_id=request_id,
            query=request.query,
            summary=summary,
            results=results,
            debug=debug,
        )

    @staticmethod
    def _candidate_for_llm(candidate: Candidate) -> dict:
        payload = candidate.payload
        return {
            "app_id": candidate.app_id,
            "name": payload.get("name"),
            "release_date": payload.get("release_date"),
            "platforms": {
                "windows": payload.get("windows", False),
                "mac": payload.get("mac", False),
                "linux": payload.get("linux", False),
            },
            "rating_percent": payload.get("rating_percent"),
            "reviews_count": payload.get("reviews_count", 0),
            "genres": payload.get("genres", []),
            "categories": payload.get("categories", []),
            "tags": payload.get("tags", [])[:20],
            "description": str(payload.get("about", ""))[:600],
            "fusion_rank": candidate.fusion_rank,
        }

    @staticmethod
    def _game_result(candidate: Candidate) -> GameResult:
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

    @staticmethod
    def _diagnostic(candidate: Candidate) -> dict:
        return {
            "app_id": candidate.app_id,
            "dense_rank": candidate.dense_rank,
            "dense_score": candidate.dense_score,
            "bm25_rank": candidate.bm25_rank,
            "bm25_score": candidate.bm25_score,
            "fusion_rank": candidate.fusion_rank,
            "fusion_score": candidate.fusion_score,
            "rerank_rank": candidate.rerank_rank,
            "rerank_score": candidate.rerank_score,
            "match_reason": candidate.match_reason,
        }
