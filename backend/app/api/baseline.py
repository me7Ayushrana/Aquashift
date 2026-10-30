"""Reference baseline plan endpoint router."""
from typing import List, Optional
from fastapi import APIRouter, Query

from backend.app.models.schemas import BaselineResponse, CropAllocationResult
from backend.app.optimizer.model import AquaShiftOptimizer

router = APIRouter(tags=["Baseline"])

# Singleton optimizer instance for service reuse
_optimizer = AquaShiftOptimizer()


@router.get("/baseline", response_model=BaselineResponse)
async def get_baseline(
    total_land_ha: float = Query(default=10.0, gt=0.0, le=1000.0, description="Farm land in hectares"),
    rainfall_scenario: str = Query(default="normal", description="Rainfall scenario (normal, deficit, severe_deficit, surplus)"),
    water_availability_ratio: float = Query(default=1.0, ge=0.05, le=2.0, description="Water availability ratio"),
) -> BaselineResponse:
    """Return the reference farm baseline plan, crop allocations, yields, and water/food/income outputs."""
    rainfall_norm = rainfall_scenario.strip().lower()
    selected_crops = _optimizer.all_crops

    # 1. Calculate baseline metrics and allocations
    baseline_areas, baseline_metrics = _optimizer.calculate_baseline(
        total_land_ha=total_land_ha,
        rainfall_scenario=rainfall_norm,
        water_availability_ratio=water_availability_ratio,
        selected_crops=selected_crops,
    )

    # 2. Get predictions for all crops under the baseline conditions
    preds = _optimizer.predictor.predict_all_crops(
        rainfall_scenario=rainfall_norm,
        water_availability_ratio=water_availability_ratio,
        crops=selected_crops,
    ).predictions

    allocations: List[CropAllocationResult] = []
    for c in selected_crops:
        area = baseline_areas.get(c, 0.0)
        land_pct = (area / total_land_ha * 100.0) if total_land_ha > 0 else 0.0
        pred = preds[c]
        y = pred.predicted_yield_t_ha
        w = pred.predicted_water_demand_m3_ha
        price = float(_optimizer.crops_df.loc[c, "price_inr_quintal"])
        cost_ha = float(_optimizer.crops_df.loc[c, "cultivation_cost_inr_ha"])
        cal_kg = float(_optimizer.crops_df.loc[c, "calories_kcal_kg"])

        prod_tonnes = round(area * y, 3)
        prod_quintals = round(prod_tonnes * 10.0, 2)
        gross_rev = round(prod_quintals * price, 1)
        c_cost = round(area * cost_ha, 1)
        net_inc = round(gross_rev - c_cost, 1)
        c_food = round(prod_tonnes * 1000.0 * cal_kg, 1)

        allocations.append(
            CropAllocationResult(
                crop_id=c,
                crop_name=str(_optimizer.crops_df.loc[c, "crop_name"]),
                allocated_ha=round(area, 3),
                land_percentage=round(land_pct, 2),
                predicted_yield_t_ha=round(y, 3),
                predicted_water_demand_m3_ha=round(w, 1),
                production_tonnes=prod_tonnes,
                production_quintals=prod_quintals,
                gross_revenue_inr=gross_rev,
                cultivation_cost_inr=c_cost,
                net_income_inr=net_inc,
                food_calories_kcal=c_food,
            )
        )

    return BaselineResponse(
        region_name="Punjab/Haryana reference region",
        total_land_ha=total_land_ha,
        rainfall_scenario=rainfall_norm,
        water_availability_ratio=water_availability_ratio,
        total_water_use_m3=baseline_metrics["total_water_use_m3"],
        total_food_kcal=baseline_metrics["total_food_kcal"],
        total_gross_revenue_inr=baseline_metrics["total_gross_revenue_inr"],
        total_cultivation_cost_inr=baseline_metrics["total_cultivation_cost_inr"],
        total_net_income_inr=baseline_metrics["total_net_income_inr"],
        allocations=allocations,
    )
