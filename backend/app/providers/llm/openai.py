import asyncio
from typing import TypeVar

from aiolimiter import AsyncLimiter
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.providers.llm.errors import FailureCategory, ProviderFailure, classify_status

T = TypeVar("T", bound=BaseModel)


class OpenAIAdapter:
    name = "openai"

    def __init__(self, api_key: str, model: str, rpm: int):
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key)
        self.limiter = AsyncLimiter(rpm, 60)

    async def generate_structured(
        self, *, system: str, user: str, response_model: type[T], timeout_seconds: float
    ) -> T:
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self.limiter:
                    response = await self.client.responses.parse(
                        model=self.model,
                        instructions=system,
                        input=user,
                        text_format=response_model,
                        reasoning={"effort": "none"},
                        timeout=timeout_seconds,
                    )
            if response.output_parsed is None:
                raise ProviderFailure(
                    "OpenAI returned no parsed output", FailureCategory.INVALID_OUTPUT, False
                )
            return response.output_parsed
        except ProviderFailure:
            raise
        except (TimeoutError, APITimeoutError) as exc:
            raise ProviderFailure("OpenAI timed out", FailureCategory.TIMEOUT, True) from exc
        except APIConnectionError as exc:
            raise ProviderFailure("OpenAI network error", FailureCategory.NETWORK, True) from exc
        except APIStatusError as exc:
            category, retryable = classify_status(exc.status_code)
            raise ProviderFailure("OpenAI request failed", category, retryable) from exc
        except ValidationError as exc:
            raise ProviderFailure(
                "OpenAI output failed validation", FailureCategory.INVALID_OUTPUT, False
            ) from exc
