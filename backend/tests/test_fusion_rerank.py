import pytest

from app.domain.search import RetrievalHit
from app.rag.fusion import weighted_rrf
from app.rag.rerank import apply_rerank
from app.schemas.llm import RerankAnswer, RerankedItem

pytestmark = pytest.mark.unit


def test_weighted_rrf_preserves_diagnostics_and_deduplicates():
    dense = [RetrievalHit(1, {"name": "one"}, 0.9), RetrievalHit(2, {}, 0.8)]
    sparse = [RetrievalHit(2, {"name": "two"}, 12), RetrievalHit(3, {}, 8)]
    result = weighted_rrf(dense, sparse, dense_weight=0.65, sparse_weight=0.35, rrf_k=60, limit=3)
    assert len(result) == 3
    item = next(candidate for candidate in result if candidate.app_id == 2)
    assert item.dense_rank == 2 and item.bm25_rank == 1
    assert item.fusion_rank is not None


def test_rerank_removes_unknown_and_duplicate_ids_then_fills():
    candidates = weighted_rrf(
        [RetrievalHit(1, {}, 1), RetrievalHit(2, {}, 0.5)],
        [],
        dense_weight=1,
        sparse_weight=0,
        rrf_k=60,
        limit=2,
    )
    output = RerankAnswer(
        summary="ok",
        ranked=[
            RerankedItem(app_id=999, score=1),
            RerankedItem(app_id=2, score=0.9),
            RerankedItem(app_id=2, score=0.8),
        ],
    )
    result = apply_rerank(candidates, output, 2)
    assert [item.app_id for item in result] == [2, 1]
    assert result[0].rerank_score == 0.9
