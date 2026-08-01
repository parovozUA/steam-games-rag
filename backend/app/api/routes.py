from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.schemas.api import IndexStatusResponse, SearchRequest, SearchResponse

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    state = request.app.state.indexing.status().state
    if state != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if state == "ready" else "not_ready", "index_state": state}


@router.get("/api/v1/index/status", response_model=IndexStatusResponse)
async def index_status(request: Request) -> IndexStatusResponse:
    return request.app.state.indexing.status()


@router.post("/api/v1/index/reindex", response_model=IndexStatusResponse, status_code=202)
async def reindex(request: Request) -> IndexStatusResponse:
    await request.app.state.indexing.reindex()
    return request.app.state.indexing.status()


@router.post("/api/v1/search", response_model=SearchResponse, response_model_exclude_none=True)
async def search(payload: SearchRequest, request: Request) -> SearchResponse:
    return await request.app.state.pipeline.search(
        payload, request_id=UUID(request.state.request_id)
    )
