"""ML crop prediction endpoint router."""
from fastapi import APIRouter

from backend.app.core.cache import scenario_cache
from backend.app.ml.predictor import AquaShiftPredictor
from backend.app.models.schemas import BatchPredictionRequest, BatchPredictionResponse

router = APIRouter(tags=["ML Prediction"])

# Singleton predictor instance for service reuse
_predictor = AquaShiftPredictor()


@router.post("/predict", response_model=BatchPredictionResponse)
async def predict_crops(request: BatchPredictionRequest) -> BatchPredictionResponse:
    """Predict yields (t/ha) and water demands (m³/ha) for crops under the specified scenario."""
    cache_key = scenario_cache.make_key("predict", request)
    cached = scenario_cache.get(cache_key)
    if cached is not None:
        return cached

    res = _predictor.predict_all_crops(
        rainfall_scenario=request.rainfall_scenario,
        water_availability_ratio=request.water_availability_ratio,
        crops=request.crops,
    )

    scenario_cache.set(cache_key, res)
    return res
