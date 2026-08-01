import asyncio
from typing import TypeVar

from aiolimiter import AsyncLimiter
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.providers.llm.errors import FailureCategory, ProviderFailure, classify_status

T = TypeVar("T", bound=BaseModel)


class GeminiAdapter:
    name = "gemini"

    def __init__(self, api_key: str, model: str, rpm: int):
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.limiter = AsyncLimiter(rpm, 60)

    async def generate_structured(
        self, *, system: str, user: str, response_model: type[T], timeout_seconds: float
    ) -> T:
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self.limiter:
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=user,
                        config=types.GenerateContentConfig(
                            system_instruction=system,
                            response_mime_type="application/json",
                            response_json_schema=response_model.model_json_schema(),
                            temperature=0,
                            thinking_config=types.ThinkingConfig(thinking_budget=0),
                        ),
                    )
            return response_model.model_validate_json(response.text)
        except TimeoutError as exc:
            raise ProviderFailure("Gemini timed out", FailureCategory.TIMEOUT, True) from exc
        except (ValidationError, TypeError) as exc:
            raise ProviderFailure(
                "Gemini output failed validation", FailureCategory.INVALID_OUTPUT, False
            ) from exc
        except ProviderFailure:
            raise
        except Exception as exc:
            status_value = getattr(exc, "status_code", 0) or getattr(exc, "code", 0) or 0
            try:
                status = int(status_value)
            except (TypeError, ValueError):
                status = 0
            if status:
                category, retryable = classify_status(status)
            elif isinstance(exc, ConnectionError | OSError):
                category, retryable = FailureCategory.NETWORK, True
            else:
                category, retryable = FailureCategory.UNKNOWN, False
            raise ProviderFailure("Gemini request failed", category, retryable) from exc
