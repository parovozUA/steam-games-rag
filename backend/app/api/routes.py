from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.schemas.api import SearchRequest

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    # Assume ready, data pipeline runs separately
    return {"status": "ready", "index_state": "ready"}


@router.post("/api/v1/search")
async def search(payload: SearchRequest, request: Request):
    generator = request.app.state.pipeline.search_stream(
        payload, request_id=UUID(request.state.request_id)
    )
    return StreamingResponse(generator, media_type="text/event-stream")
