"""Parametric water availability sweep endpoint router."""
from typing import Optional
from fastapi import APIRouter

from backend.app.core.cache import scenario_cache
from backend.app.models.schemas import SweepRequest, SweepResponse
from backend.app.optimizer.model import AquaShiftOptimizer
from backend.app.optimizer.sweep import AquaShiftWaterSweep

router = APIRouter(tags=["Simulation"])

# Singleton water sweep instance
_optimizer = AquaShiftOptimizer()
_sweep = AquaShiftWaterSweep(optimizer=_optimizer)


@router.post("/simulate/sweep", response_model=SweepResponse)
async def simulate_water_sweep(
    request: Optional[SweepRequest] = None,
) -> SweepResponse:
    """Run parametric water availability sweep from 100% down to 20% of baseline water availability."""
    cache_key = scenario_cache.make_key("sweep", request or {})
    cached = scenario_cache.get(cache_key)
    if cached is not None:
        return cached

    response = _sweep.run_sweep(request=request)
    scenario_cache.set(cache_key, response)
    return response
