import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from app.core.config import Settings

logger = logging.getLogger(__name__)


class NoOpObservation:
    """Null-object pattern for tracing when Langfuse is disabled or unavailable."""

    def update(self, **kwargs: Any) -> "NoOpObservation":
        return self

    def end(self, **kwargs: Any) -> None:
        pass


class TracingService:
    """Service managing Langfuse client initialization, traces, and spans with fail-open safety."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

        if settings.is_langfuse_configured:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_server_url,
                    environment=settings.environment,
                    debug=False,
                )
                logger.info(
                    "langfuse_initialized",
                    extra={
                        "host": settings.langfuse_server_url,
                        "environment": settings.environment,
                    },
                )
            except Exception as exc:
                logger.warning("langfuse_init_failed", extra={"error": str(exc)})
                self._client = None
        else:
            logger.info("langfuse_disabled_or_unconfigured")

    @property
    def is_active(self) -> bool:
        return self._client is not None

    @contextmanager
    def start_trace(
        self,
        *,
        name: str = "steam-game-search",
        request_id: UUID | str | None = None,
        input_data: Any = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Start a top-level search trace."""
        if not self._client:
            yield NoOpObservation()
            return

        trace_tags = ["rag", "steam-games", self.settings.environment]
        if tags:
            trace_tags.extend(tags)

        trace_meta = {"environment": self.settings.environment}
        if metadata:
            trace_meta.update(metadata)

        trace_context = None
        if request_id:
            if isinstance(request_id, UUID):
                trace_context = {"trace_id": request_id.hex}
            else:
                try:
                    trace_context = {"trace_id": UUID(str(request_id)).hex}
                except ValueError:
                    clean_id = str(request_id).replace("-", "").strip()
                    if len(clean_id) == 32 and all(c in "0123456789abcdefABCDEF" for c in clean_id):
                        trace_context = {"trace_id": clean_id.lower()}
                    else:
                        trace_meta["request_id"] = str(request_id)

        try:
            with self._client.start_as_current_observation(
                name=name,
                as_type="chain",
                input=input_data,
                metadata=trace_meta,
                trace_context=trace_context,
            ) as span:
                yield span
        except Exception as exc:
            logger.warning("langfuse_trace_error", extra={"error": str(exc), "trace_name": name})
            yield NoOpObservation()

    @contextmanager
    def span(
        self,
        *,
        name: str,
        as_type: str = "span",
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Create a child span or retriever/embedding observation."""
        if not self._client:
            yield NoOpObservation()
            return

        try:
            with self._client.start_as_current_observation(
                name=name,
                as_type=as_type,
                input=input_data,
                metadata=metadata,
            ) as span:
                yield span
        except Exception as exc:
            logger.warning("langfuse_span_error", extra={"error": str(exc), "span_name": name})
            yield NoOpObservation()

    @contextmanager
    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
        model_parameters: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Create a generation observation for LLM calls with token tracking."""
        if not self._client:
            yield NoOpObservation()
            return

        try:
            with self._client.start_as_current_observation(
                name=name,
                as_type="generation",
                model=model or self.settings.gemini_model,
                input=input_data,
                metadata=metadata,
                model_parameters=model_parameters,
            ) as gen:
                yield gen
        except Exception as exc:
            logger.warning("langfuse_generation_error", extra={"error": str(exc), "gen_name": name})
            yield NoOpObservation()

    def flush(self) -> None:
        """Flush pending events to Langfuse."""
        if self._client:
            try:
                self._client.flush()
            except Exception as exc:
                logger.warning("langfuse_flush_error", extra={"error": str(exc)})

    def shutdown(self) -> None:
        """Gracefully shut down the Langfuse client."""
        if self._client:
            try:
                self._client.shutdown()
            except Exception as exc:
                logger.warning("langfuse_shutdown_error", extra={"error": str(exc)})
