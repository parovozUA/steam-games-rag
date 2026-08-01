import asyncio

import pytest

from app.core.deadline import Deadline
from app.core.errors import DeadlineExceededError, LLMUnavailableError
from app.providers.llm.errors import FailureCategory, ProviderFailure, classify_status
from app.schemas.filters import QueryUnderstanding
from app.services.llm_routing import SearchLLMSession

pytestmark = pytest.mark.unit


class FakeProvider:
    def __init__(self, name, outcomes):
        self.name = name
        self.model = f"{name}-model"
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class SlowProvider(FakeProvider):
    async def generate_structured(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.2)
        return understood()


def understood():
    return QueryUnderstanding(detected_language="en", rewritten_query_en="space", filters={})


def test_retryable_status_classification():
    assert classify_status(429) == (FailureCategory.RATE_LIMIT, True)
    assert classify_status(503) == (FailureCategory.SERVER, True)
    assert classify_status(401) == (FailureCategory.AUTH, False)
    assert classify_status(400) == (FailureCategory.INVALID_REQUEST, False)


@pytest.mark.asyncio
async def test_gemini_attempt_budget_is_shared_between_stages():
    retryable = ProviderFailure("retry", FailureCategory.SERVER, True)
    gemini = FakeProvider("gemini", [understood(), retryable, retryable])
    openai = FakeProvider("openai", [understood()])
    session = SearchLLMSession(gemini, openai, Deadline.after(2), "r")
    await session.call("one", system="", user="", response_model=QueryUnderstanding)
    await session.call("two", system="", user="", response_model=QueryUnderstanding)
    assert gemini.calls == 3
    assert openai.calls == 1
    assert session.fallback_activated


@pytest.mark.asyncio
async def test_nonretryable_failure_falls_back_immediately_and_stays_sticky():
    invalid = ProviderFailure("invalid", FailureCategory.INVALID_OUTPUT, False)
    gemini = FakeProvider("gemini", [invalid])
    openai = FakeProvider("openai", [understood(), understood()])
    session = SearchLLMSession(gemini, openai, Deadline.after(2), "r")
    await session.call("one", system="", user="", response_model=QueryUnderstanding)
    await session.call("two", system="", user="", response_model=QueryUnderstanding)
    assert gemini.calls == 1 and openai.calls == 2


@pytest.mark.asyncio
async def test_global_deadline_cancels_slow_work():
    with pytest.raises(DeadlineExceededError):
        await Deadline.after(0.01).run(asyncio.sleep(1))


@pytest.mark.asyncio
async def test_soft_deadline_switches_to_fallback_before_hard_deadline():
    gemini = SlowProvider("gemini", [])
    openai = FakeProvider("openai", [understood()])
    session = SearchLLMSession(
        gemini,
        openai,
        Deadline.after(1),
        "r",
        soft_deadline=Deadline.after(0.08),
    )
    result = await session.call("one", system="", user="", response_model=QueryUnderstanding)
    assert result.rewritten_query_en == "space"
    assert gemini.calls == 1 and openai.calls == 1
    assert session.fallback_activated


@pytest.mark.asyncio
async def test_both_provider_failures_return_typed_unavailable_error():
    failure = ProviderFailure("auth", FailureCategory.AUTH, False)
    gemini = FakeProvider("gemini", [failure])
    openai = FakeProvider("openai", [failure])
    session = SearchLLMSession(gemini, openai, Deadline.after(1), "r")
    with pytest.raises(LLMUnavailableError):
        await session.call("one", system="", user="", response_model=QueryUnderstanding)
