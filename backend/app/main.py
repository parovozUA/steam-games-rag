import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.observability.logging import configure_logging
from app.prompts.loader import PromptLoader
from app.providers.embeddings.local import LocalEmbeddingProvider
from app.providers.llm.gemini import GeminiAdapter
from app.providers.llm.openai import OpenAIAdapter
from app.providers.llm.unavailable import UnavailableLLMAdapter
from app.providers.vector_store.qdrant import QdrantVectorStore
from app.rag.pipeline import SearchPipeline
from app.services.indexing import IndexingCoordinator

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    prompts = PromptLoader(settings.prompt_registry_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        embeddings = LocalEmbeddingProvider(
            settings.dense_embedding_model,
            settings.sparse_embedding_model,
            settings.embedding_batch_size,
            settings.dense_vector_size,
        )
        vector_store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection)
        indexing = IndexingCoordinator(
            vector_store=vector_store,
            embeddings=embeddings,
            csv_path=settings.steam_csv_path,
            catalog_path=settings.canonical_catalog_path,
            state_path=settings.index_state_path,
            batch_size=settings.ingestion_batch_size,
            max_retrieval_chars=settings.retrieval_text_max_chars,
        )
        gemini = (
            GeminiAdapter(settings.gemini_api_key, settings.gemini_model, settings.gemini_rpm)
            if settings.gemini_api_key
            else UnavailableLLMAdapter("gemini", settings.gemini_model)
        )
        openai = (
            OpenAIAdapter(settings.openai_api_key, settings.openai_model, settings.openai_rpm)
            if settings.openai_api_key
            else UnavailableLLMAdapter("openai", settings.openai_model)
        )
        app.state.indexing = indexing
        app.state.pipeline = SearchPipeline(
            settings=settings,
            indexing=indexing,
            embeddings=embeddings,
            vector_store=vector_store,
            prompts=prompts,
            gemini=gemini,
            openai=openai,
            catalog=lambda: indexing.catalog,
        )
        await indexing.initialize(settings.qdrant_startup_timeout_seconds)
        yield
        await vector_store.close()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return ORJSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": exc.request_id or request.state.request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return ORJSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": ErrorCode.INVALID_QUERY,
                    "message": "The search request is invalid",
                    "request_id": request.state.request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled_request_error",
            extra={"request_id": request.state.request_id, "failure_category": "internal"},
        )
        return ORJSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR,
                    "message": "An unexpected internal error occurred",
                    "request_id": request.state.request_id,
                }
            },
        )

    app.include_router(router)
    return app


app = create_app()
