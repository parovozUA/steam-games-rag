from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RetrievalHit:
    app_id: int
    payload: dict[str, Any]
    score: float


@dataclass(slots=True)
class Candidate:
    app_id: int
    payload: dict[str, Any]
    dense_rank: int | None = None
    dense_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    fusion_rank: int | None = None
    fusion_score: float = 0.0
    rerank_rank: int | None = None
    rerank_score: float | None = None
    match_reason: str | None = None
