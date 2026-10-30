"""Extreme scenario stress-test endpoint router."""
from typing import Optional
from fastapi import APIRouter, Body

from backend.app.core.cache import scenario_cache
from backend.app.models.schemas import OptimizationRequest, StressTestResponse
from backend.app.optimizer.model import AquaShiftOptimizer
from backend.app.optimizer.stress import AquaShiftStressTester

router = APIRouter(tags=["Stress Test"])

# Singleton stress tester instance
_optimizer = AquaShiftOptimizer()
_tester = AquaShiftStressTester(optimizer=_optimizer)


@router.post("/stress-test", response_model=StressTestResponse)
async def run_stress_test(
    request: Optional[OptimizationRequest] = Body(default=None),
) -> StressTestResponse:
    """Execute extreme scenario stress test comparing strict vs soft recovery solve with bottleneck diagnosis."""
    # Determine whether custom stress parameters were supplied, or if default extreme stress test is requested
    is_default = (
        request is None
        or (
            request.water_budget_m3 is None
            and request.water_budget_reduction_pct is None
            and request.food_target_kcal is None
            and request.food_target_increase_pct is None
            and request.income_target_inr is None
            and request.income_target_increase_pct is None
            and request.rainfall_scenario == "normal"
            and request.water_availability_ratio is None
        )
    )

    req_to_pass = None if is_default else request

    cache_key = scenario_cache.make_key("stress", req_to_pass or "default_extreme")
    cached = scenario_cache.get(cache_key)
    if cached is not None:
        return cached

    response = _tester.run_stress_test(request=req_to_pass)
    scenario_cache.set(cache_key, response)
    return response
