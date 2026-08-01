from app.domain.search import Candidate, RetrievalHit


def weighted_rrf(
    dense: list[RetrievalHit],
    sparse: list[RetrievalHit],
    *,
    dense_weight: float,
    sparse_weight: float,
    rrf_k: int,
    limit: int,
) -> list[Candidate]:
    candidates: dict[int, Candidate] = {}
    for rank, hit in enumerate(dense, 1):
        candidate = candidates.setdefault(hit.app_id, Candidate(hit.app_id, hit.payload))
        candidate.dense_rank = rank
        candidate.dense_score = hit.score
        candidate.fusion_score += dense_weight / (rrf_k + rank)
    for rank, hit in enumerate(sparse, 1):
        candidate = candidates.setdefault(hit.app_id, Candidate(hit.app_id, hit.payload))
        candidate.bm25_rank = rank
        candidate.bm25_score = hit.score
        candidate.fusion_score += sparse_weight / (rrf_k + rank)
    ordered = sorted(candidates.values(), key=lambda item: (-item.fusion_score, item.app_id))
    for rank, candidate in enumerate(ordered, 1):
        candidate.fusion_rank = rank
    return ordered[:limit]
