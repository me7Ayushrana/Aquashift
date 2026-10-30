"""API router aggregation."""
from fastapi import APIRouter

from backend.app.api.baseline import router as baseline_router
from backend.app.api.config import router as config_router
from backend.app.api.health import router as health_router
from backend.app.api.optimize import router as optimize_router
from backend.app.api.predict import router as predict_router
from backend.app.api.stress import router as stress_router
from backend.app.api.sweep import router as sweep_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(config_router)
api_router.include_router(baseline_router)
api_router.include_router(predict_router)
api_router.include_router(optimize_router)
api_router.include_router(stress_router)
api_router.include_router(sweep_router)

__all__ = ["api_router"]
