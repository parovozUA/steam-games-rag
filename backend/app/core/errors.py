from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_QUERY = "INVALID_QUERY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class AppError(Exception):
    code: ErrorCode
    message: str
    status_code: int
    request_id: str | None = None
