from app.domain.search import Candidate
from app.schemas.llm import RerankAnswer


def apply_rerank(candidates: list[Candidate], output: RerankAnswer, limit: int) -> list[Candidate]:
    by_id = {candidate.app_id: candidate for candidate in candidates}
    ordered: list[Candidate] = []
    seen: set[int] = set()
    for item in output.ranked:
        candidate = by_id.get(item.app_id)
        if candidate is None or item.app_id in seen:
            continue
        candidate.rerank_score = item.score
        candidate.match_reason = item.match_reason
        ordered.append(candidate)
        seen.add(item.app_id)
    ordered.extend(candidate for candidate in candidates if candidate.app_id not in seen)
    for rank, candidate in enumerate(ordered, 1):
        candidate.rerank_rank = rank
    return ordered[:limit]
