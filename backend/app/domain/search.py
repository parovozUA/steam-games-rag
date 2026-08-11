from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RetrievalHit:
    app_id: int
    payload: dict[str, Any]
    score: float
