"""Health check endpoint router."""
from fastapi import APIRouter
from backend.app.core.config import settings
from backend.app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return application health, version, and operational status."""
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        service="AquaShift Backend",
        offline_mode=True,
    )
