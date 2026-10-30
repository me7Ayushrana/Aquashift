"""Health check endpoint router."""
from fastapi import APIRouter
from backend.app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return application health status."""
    return HealthResponse(status="ok")
