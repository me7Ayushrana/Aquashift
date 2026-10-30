"""OR-Tools optimization endpoint router."""
from fastapi import APIRouter

from backend.app.core.cache import scenario_cache
from backend.app.models.schemas import OptimizationRequest, OptimizationResponse
from backend.app.optimizer.model import AquaShiftOptimizer

router = APIRouter(tags=["Optimization"])

# Singleton optimizer instance
_optimizer = AquaShiftOptimizer()


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_plan(request: OptimizationRequest) -> OptimizationResponse:
    """Run deterministic OR-Tools GLOP linear solver to optimize crop allocations and return KPI impact."""
    cache_key = scenario_cache.make_key("optimize", request)
    cached = scenario_cache.get(cache_key)
    if cached is not None:
        return cached

    response = _optimizer.optimize(request)
    scenario_cache.set(cache_key, response)
    return response
