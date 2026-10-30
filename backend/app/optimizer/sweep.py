"""Water availability sweep simulator for analyzing trade-offs across water stress levels.

Parametrically executes OR-Tools optimization across water availability ratios
(typically 100% down to 20%), returning structured trade-off curve points.
"""
from typing import List, Optional

from backend.app.models.schemas import (
    OptimizationRequest,
    SweepPoint,
    SweepRequest,
    SweepResponse,
)
from backend.app.optimizer.model import AquaShiftOptimizer


class AquaShiftWaterSweep:
    """Executes parametric water sweeps from 100% down to 20% of baseline water availability."""

    def __init__(self, optimizer: Optional[AquaShiftOptimizer] = None):
        self.optimizer = optimizer or AquaShiftOptimizer()

    def run_sweep(self, request: Optional[SweepRequest] = None) -> SweepResponse:
        """Run parametric water availability sweep and return ordered trade-off points.

        Args:
            request: Optional configuration of sweep bounds, step, scenario, and land.
                     Defaults to 10 ha, normal rainfall, 1.0 down to 0.20 in 0.10 steps.

        Returns:
            SweepResponse containing ordered SweepPoints and tipping point detection.
        """
        req = request or SweepRequest()
        total_land_ha = float(req.total_land_ha)
        rainfall_scenario = req.rainfall_scenario.lower()
        selected_crops = [c.lower() for c in (req.selected_crops or self.optimizer.all_crops)]

        # 1. Calculate baseline reference targets under normal 100% conditions
        _, baseline = self.optimizer.calculate_baseline(
            total_land_ha=total_land_ha,
            rainfall_scenario="normal",
            water_availability_ratio=1.0,
            selected_crops=selected_crops,
        )

        b_water = baseline["total_water_use_m3"]
        b_food = baseline["total_food_kcal"]
        b_income = baseline["total_net_income_inr"]

        # 2. Generate monotonically decreasing ratios from start_ratio down to end_ratio
        ratios = []
        cur = req.start_ratio
        while cur >= req.end_ratio - 1e-5:
            ratios.append(round(cur, 2))
            cur -= req.step

        points: List[SweepPoint] = []
        tipping_point_ratio: Optional[float] = None
        tipping_point_desc: Optional[str] = None

        for ratio in ratios:
            cut_pct = round((1.0 - ratio) * 100.0, 1)
            water_budget = round(b_water * ratio, 1)

            opt_req = OptimizationRequest(
                total_land_ha=total_land_ha,
                water_budget_m3=water_budget,
                food_target_kcal=b_food,
                income_target_inr=b_income,
                rainfall_scenario=rainfall_scenario,
                water_availability_ratio=ratio,
                selected_crops=selected_crops,
                optimization_mode=req.optimization_mode,
                weights=req.weights,
            )

            res = self.optimizer.optimize(opt_req)

            alloc_ha = {a.crop_id: a.allocated_ha for a in res.allocations}
            alloc_pct = {a.crop_id: a.land_percentage for a in res.allocations}

            point = SweepPoint(
                water_availability_ratio=ratio,
                water_budget_reduction_pct=cut_pct,
                water_budget_m3=res.water_budget_m3,
                total_water_use_m3=res.total_water_use_m3,
                water_slack_m3=res.water_slack_m3,
                total_food_kcal=res.total_food_kcal,
                food_slack_kcal=res.food_slack_kcal,
                total_net_income_inr=res.total_net_income_inr,
                income_slack_inr=res.income_slack_inr,
                allocations_ha=alloc_ha,
                allocations_pct=alloc_pct,
                primary_bottleneck=res.diagnosis.primary_bottleneck,
                all_targets_met=res.diagnosis.all_targets_met,
            )
            points.append(point)

            # Detect first tipping point where targets can no longer be satisfied without slack
            if not res.diagnosis.all_targets_met and tipping_point_ratio is None:
                tipping_point_ratio = ratio
                bn = res.diagnosis.primary_bottleneck or "Resource"
                tipping_point_desc = (
                    f"Tipping point at {ratio * 100:.0f}% water availability (-{cut_pct:.0f}% water budget): "
                    f"{bn} bottleneck emerges; farm can no longer meet baseline targets without slack."
                )

        return SweepResponse(
            total_land_ha=total_land_ha,
            rainfall_scenario=rainfall_scenario,
            baseline_water_m3=b_water,
            baseline_food_kcal=b_food,
            baseline_income_inr=b_income,
            points=points,
            tipping_point_water_ratio=tipping_point_ratio,
            tipping_point_description=tipping_point_desc,
        )
