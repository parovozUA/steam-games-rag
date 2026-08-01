from enum import StrEnum


class FailureCategory(StrEnum):
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    NETWORK = "network"
    TIMEOUT = "timeout"
    AUTH = "authentication"
    INVALID_REQUEST = "invalid_request"
    INVALID_OUTPUT = "invalid_output"
    UNKNOWN = "unknown"


class ProviderFailure(Exception):
    def __init__(self, message: str, category: FailureCategory, retryable: bool):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


def classify_status(status_code: int) -> tuple[FailureCategory, bool]:
    if status_code == 429:
        return FailureCategory.RATE_LIMIT, True
    if status_code >= 500:
        return FailureCategory.SERVER, True
    if status_code in {401, 403}:
        return FailureCategory.AUTH, False
    return FailureCategory.INVALID_REQUEST, False
