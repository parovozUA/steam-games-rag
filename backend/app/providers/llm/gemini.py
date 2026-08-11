import asyncio
from typing import TypeVar

from aiolimiter import AsyncLimiter
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, ValidationError

from app.providers.llm.errors import FailureCategory, ProviderFailure

T = TypeVar("T", bound=BaseModel)

def classify_gemini_status(status_code: int) -> tuple[FailureCategory, bool]:
    if status_code == 429:
        return FailureCategory.RATE_LIMIT, True
    if status_code >= 500:
        return FailureCategory.SERVER, True
    if status_code in {401, 403}:
        return FailureCategory.AUTH, False
    return FailureCategory.INVALID_REQUEST, False

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
                            response_schema=response_model,
                            temperature=0.1,
                        )
                    )
            if not response.text:
                raise ProviderFailure(
                    "Gemini returned no output", FailureCategory.INVALID_OUTPUT, False
                )
            
            try:
                return response_model.model_validate_json(response.text)
            except ValidationError as exc:
                raise ProviderFailure(
                    "Gemini output failed validation", FailureCategory.INVALID_OUTPUT, False
                ) from exc
        except ProviderFailure:
            raise
        except TimeoutError as exc:
            raise ProviderFailure("Gemini timed out", FailureCategory.TIMEOUT, True) from exc
        except APIError as exc:
            category, retryable = classify_gemini_status(exc.code)
            raise ProviderFailure(f"Gemini request failed: {exc.message}", category, retryable) from exc

    async def stream_chat(
        self, *, system: str, user: str, timeout_seconds: float
    ):
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self.limiter:
                    stream = await self.client.aio.models.generate_content_stream(
                        model=self.model,
                        contents=user,
                        config=types.GenerateContentConfig(
                            system_instruction=system,
                        )
                    )
                    async for chunk in stream:
                        if chunk.text:
                            yield chunk.text
        except TimeoutError as exc:
            raise ProviderFailure("Gemini timed out", FailureCategory.TIMEOUT, True) from exc
        except APIError as exc:
            category, retryable = classify_gemini_status(exc.code)
            raise ProviderFailure(f"Gemini request failed: {exc.message}", category, retryable) from exc
