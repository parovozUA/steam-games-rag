from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_QUERY = "INVALID_QUERY"
    INDEX_NOT_READY = "INDEX_NOT_READY"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class AppError(Exception):
    code: ErrorCode
    message: str
    status_code: int
    request_id: str | None = None


class IndexNotReadyError(AppError):
    def __init__(
        self, message: str = "The search index is not ready", request_id: str | None = None
    ):
        super().__init__(ErrorCode.INDEX_NOT_READY, message, 503, request_id)


class LLMUnavailableError(AppError):
    def __init__(self, message: str = "Language-model providers are unavailable"):
        super().__init__(ErrorCode.LLM_UNAVAILABLE, message, 503)


class DeadlineExceededError(AppError):
    def __init__(self, message: str = "The search deadline was exceeded"):
        super().__init__(ErrorCode.DEADLINE_EXCEEDED, message, 504)
