from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.search import RetrievalHit
from app.prompts.loader import PromptLoader
from app.rag.pipeline import SearchPipeline
from app.schemas.api import IndexStatusResponse, SearchRequest
from app.schemas.filters import QueryUnderstanding, SearchFilters
from app.schemas.llm import RerankAnswer, RerankedItem
from app.services.canonicalization import CanonicalCatalog

pytestmark = pytest.mark.unit


class ReadyIndex:
    def status(self):
        return IndexStatusResponse(state="ready", point_count=1)


class FakeEmbedding:
    async def embed_query(self, text):
        return [1.0, 0.0]

    async def sparse_query(self, text):
        return ([1], [1.0])


class FakeStore:
    payload = {
        "name": "Orbit Together",
        "release_date": "2022-01-10",
        "about": "Space co-op",
        "windows": True,
        "mac": False,
        "linux": True,
        "rating_percent": 90,
        "reviews_count": 1000,
        "developers": [],
        "publishers": [],
        "genres": ["Adventure"],
        "categories": ["Co-op"],
        "tags": ["Space"],
    }

    async def dense_search(self, vector, filters, limit):
        return [RetrievalHit(10, self.payload, 0.9)]

    async def sparse_search(self, vector, filters, limit):
        return [RetrievalHit(10, self.payload, 5)]


class FakeLLM:
    name = "fake"
    model = "fake-1"

    async def generate_structured(self, *, response_model, **kwargs):
        if response_model is QueryUnderstanding:
            return QueryUnderstanding(
                detected_language="en", rewritten_query_en="space co-op", filters=SearchFilters()
            )
        return RerankAnswer(
            summary="A strong space co-op match.", ranked=[RerankedItem(app_id=10, score=0.95)]
        )


def pipeline():
    root = Path(__file__).parents[2]
    settings = Settings(
        prompt_registry_path=root / "prompts" / "registry.yaml",
        result_limit=1,
        rerank_candidates=1,
        fusion_top_k=1,
        dense_top_k=1,
        sparse_top_k=1,
    )
    return SearchPipeline(
        settings=settings,
        indexing=ReadyIndex(),
        embeddings=FakeEmbedding(),
        vector_store=FakeStore(),
        prompts=PromptLoader(settings.prompt_registry_path),
        gemini=FakeLLM(),
        openai=FakeLLM(),
        catalog=lambda: CanonicalCatalog(),
    )


@pytest.mark.asyncio
async def test_debug_is_excluded_by_default():
    result = await pipeline().search(SearchRequest(query="space", debug=False))
    assert result.debug is None
    assert "debug" not in result.model_dump(exclude_none=True)


@pytest.mark.asyncio
async def test_debug_contains_retrieval_and_provider_diagnostics():
    result = await pipeline().search(SearchRequest(query="space", debug=True))
    assert result.debug["detected_language"] == "en"
    assert result.debug["retrieval"][0]["dense_rank"] == 1
    assert result.debug["providers"]["rerank_and_answer"]["model"] == "fake-1"
