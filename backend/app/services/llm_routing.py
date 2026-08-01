import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from app.core.deadline import Deadline
from app.core.errors import DeadlineExceededError, LLMUnavailableError
from app.providers.llm.errors import ProviderFailure
from app.providers.protocols import LLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMStageDiagnostic:
    provider: str
    model: str
    duration_ms: float


@dataclass
class SearchLLMSession:
    gemini: LLMProvider
    openai: LLMProvider
    deadline: Deadline
    request_id: str
    soft_deadline: Deadline | None = None
    max_gemini_attempts: int = 3
    gemini_attempts: int = 0
    fallback_activated: bool = False
    stages: dict[str, LLMStageDiagnostic] = field(default_factory=dict)

    async def call(
        self,
        stage: str,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> T:
        if not self.fallback_activated:
            while self.gemini_attempts < self.max_gemini_attempts:
                self.deadline.require()
                gemini_remaining = min(
                    self.deadline.remaining(),
                    self.soft_deadline.remaining()
                    if self.soft_deadline
                    else self.deadline.remaining(),
                )
                if gemini_remaining < 0.05:
                    break
                self.gemini_attempts += 1
                started = time.monotonic()
                try:
                    result = await asyncio.wait_for(
                        self.gemini.generate_structured(
                            system=system,
                            user=user,
                            response_model=response_model,
                            timeout_seconds=gemini_remaining,
                        ),
                        timeout=gemini_remaining,
                    )
                    self.stages[stage] = LLMStageDiagnostic(
                        self.gemini.name,
                        self.gemini.model,
                        round((time.monotonic() - started) * 1000, 2),
                    )
                    return result
                except TimeoutError as exc:
                    if self.deadline.remaining() < 0.05:
                        raise DeadlineExceededError() from exc
                    break
                except ProviderFailure as exc:
                    logger.warning(
                        "llm_attempt_failed",
                        extra={
                            "request_id": self.request_id,
                            "pipeline_stage": stage,
                            "provider": self.gemini.name,
                            "model": self.gemini.model,
                            "attempt": self.gemini_attempts,
                            "failure_category": exc.category,
                            "duration": time.monotonic() - started,
                        },
                    )
                    if not exc.retryable or self.gemini_attempts >= self.max_gemini_attempts:
                        break
                    delay = min(
                        0.15 * (2 ** (self.gemini_attempts - 1)) + random.uniform(0, 0.08),
                        max(0, self.deadline.remaining() - 0.1),
                        max(
                            0,
                            (self.soft_deadline.remaining() if self.soft_deadline else 999) - 0.1,
                        ),
                    )
                    if delay <= 0:
                        if self.deadline.remaining() < 0.05:
                            raise DeadlineExceededError() from exc
                        break
                    await asyncio.sleep(delay)
            self.fallback_activated = True

        self.deadline.require()
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.openai.generate_structured(
                    system=system,
                    user=user,
                    response_model=response_model,
                    timeout_seconds=self.deadline.require(),
                ),
                timeout=self.deadline.require(),
            )
            self.stages[stage] = LLMStageDiagnostic(
                self.openai.name,
                self.openai.model,
                round((time.monotonic() - started) * 1000, 2),
            )
            return result
        except TimeoutError as exc:
            raise DeadlineExceededError() from exc
        except ProviderFailure as exc:
            logger.warning(
                "llm_fallback_failed",
                extra={
                    "request_id": self.request_id,
                    "pipeline_stage": stage,
                    "provider": self.openai.name,
                    "model": self.openai.model,
                    "attempt": 1,
                    "failure_category": exc.category,
                    "duration": time.monotonic() - started,
                },
            )
            if self.deadline.remaining() <= 0:
                raise DeadlineExceededError() from exc
            raise LLMUnavailableError() from exc
