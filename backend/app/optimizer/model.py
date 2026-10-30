"""AquaShift OR-Tools Crop-Allocation Optimization Engine.

Implements deterministic linear programming using Google OR-Tools `pywraplp`
with the continuous GLOP solver. Integrates ML yield and irrigation demand
predictions as inputs to decide optimal crop-area allocations.
"""
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp

from backend.app.ml.predictor import AquaShiftPredictor
from backend.app.models.schemas import (
    BindingConstraint,
    CropAllocationResult,
    LocalModelSensitivity,
    MetricComparison,
    OptimizationMode,
    OptimizationRequest,
    OptimizationResponse,
    OptimizationWeights,
)
from backend.app.optimizer.diagnosis import AquaShiftDiagnostician

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DATA_DIR = ROOT_DIR / "data"


class OptimizationValidationException(ValueError):
    """Raised when hard constraints or scenario parameters are mathematically infeasible."""

    def __init__(
        self,
        message: str,
        conflicting_constraints: Optional[List[str]] = None,
        error_code: str = "HARD_CONSTRAINTS_INFEASIBLE",
    ):
        super().__init__(message)
        self.message = message
        self.conflicting_constraints = conflicting_constraints or []
        self.error_code = error_code


class AquaShiftOptimizer:
    """Core mathematical programming optimization engine for crop allocation."""

    def __init__(
        self,
        predictor: Optional[AquaShiftPredictor] = None,
        data_dir: Optional[Path] = None,
    ):
        self.data_dir = Path(data_dir or DEFAULT_DATA_DIR)
        self.predictor = predictor or AquaShiftPredictor(data_dir=self.data_dir)

        # Load reference crop metadata
        crops_df = pd.read_csv(self.data_dir / "crops.csv")
        self.crops_df = crops_df.set_index("crop_id")
        self.all_crops: List[str] = list(self.crops_df.index)

    def validate_hard_constraints(
        self,
        total_land_ha: float,
        selected_crops: List[str],
    ) -> None:
        """Validate feasibility of hard constraints prior to invoking the solver.

        Args:
            total_land_ha: Total farm land in hectares.
            selected_crops: List of crop IDs allowed for allocation.

        Raises:
            OptimizationValidationException: If hard constraints cannot be satisfied.
        """
        if total_land_ha <= 0.0:
            raise OptimizationValidationException(
                f"Total available land must be strictly positive, got {total_land_ha:.2f} ha.",
                conflicting_constraints=["total_land_ha"],
                error_code="INVALID_LAND_AREA",
            )

        if not selected_crops:
            raise OptimizationValidationException(
                "At least one crop must be selected for allocation.",
                conflicting_constraints=["selected_crops"],
                error_code="EMPTY_CROP_SELECTION",
            )

        for c in selected_crops:
            if c not in self.all_crops:
                raise OptimizationValidationException(
                    f"Unknown crop '{c}'. Available crops: {self.all_crops}",
                    conflicting_constraints=[f"crop_{c}"],
                    error_code="UNKNOWN_CROP",
                )

        # Check bounds validity
        sum_min_share = sum(float(self.crops_df.loc[c, "min_land_share"]) for c in selected_crops)
        sum_max_share = sum(float(self.crops_df.loc[c, "max_land_share"]) for c in selected_crops)

        for c in selected_crops:
            min_s = float(self.crops_df.loc[c, "min_land_share"])
            max_s = float(self.crops_df.loc[c, "max_land_share"])
            if min_s > max_s:
                raise OptimizationValidationException(
                    f"Crop '{c}' has minimum share ({min_s:.2f}) greater than maximum share ({max_s:.2f}).",
                    conflicting_constraints=[f"bounds_{c}"],
                    error_code="INVALID_CROP_BOUNDS",
                )

        if sum_min_share > 1.0 + 1e-6:
            raise OptimizationValidationException(
                f"Sum of minimum land shares ({sum_min_share:.2f}) exceeds 1.00. "
                f"Cannot allocate {total_land_ha:.1f} ha without violating crop minimums.",
                conflicting_constraints=["min_land_shares_sum"],
                error_code="MIN_SHARES_EXCEED_TOTAL_LAND",
            )

        if sum_max_share < 1.0 - 1e-6:
            raise OptimizationValidationException(
                f"Sum of maximum land shares ({sum_max_share:.2f}) is strictly less than 1.00. "
                f"Selected crops cannot fully utilize the available {total_land_ha:.1f} ha.",
                conflicting_constraints=["max_land_shares_sum"],
                error_code="MAX_SHARES_UNDERUTILIZE_LAND",
            )

    def calculate_baseline(
        self,
        total_land_ha: float,
        rainfall_scenario: str,
        water_availability_ratio: float,
        selected_crops: List[str],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Calculate the reference baseline allocation and its agronomic/economic outputs.

        Reference Punjab/Haryana baseline:
        - 70% Paddy, 30% Maize (or Wheat if Maize is unavailable).
        """
        # Determine baseline crop distribution
        paddy_share = 0.70
        secondary_share = 0.30

        secondary_crop = "maize" if "maize" in selected_crops else ("wheat" if "wheat" in selected_crops else selected_crops[0])
        primary_crop = "paddy" if "paddy" in selected_crops else selected_crops[-1]

        baseline_areas = {
            primary_crop: paddy_share * total_land_ha,
            secondary_crop: secondary_share * total_land_ha,
        }

        # Predict yields and water demands under baseline normal scenario
        normal_preds = self.predictor.predict_all_crops(
            rainfall_scenario=rainfall_scenario,
            water_availability_ratio=water_availability_ratio,
            crops=list(baseline_areas.keys()),
        ).predictions

        b_water = 0.0
        b_food = 0.0
        b_rev = 0.0
        b_cost = 0.0

        for c, area in baseline_areas.items():
            pred = normal_preds[c]
            y = pred.predicted_yield_t_ha
            w = pred.predicted_water_demand_m3_ha
            price = float(self.crops_df.loc[c, "price_inr_quintal"])
            cost = float(self.crops_df.loc[c, "cultivation_cost_inr_ha"])
            cal = float(self.crops_df.loc[c, "calories_kcal_kg"])

            tonnes = area * y
            quintals = tonnes * 10.0
            rev = quintals * price
            c_cost = area * cost

            b_water += area * w
            b_food += tonnes * 1000.0 * cal
            b_rev += rev
            b_cost += c_cost

        b_income = b_rev - b_cost

        baseline_metrics = {
            "total_land_ha": total_land_ha,
            "total_water_use_m3": round(b_water, 1),
            "total_food_kcal": round(b_food, 1),
            "total_gross_revenue_inr": round(b_rev, 1),
            "total_cultivation_cost_inr": round(b_cost, 1),
            "total_net_income_inr": round(b_income, 1),
        }

        return baseline_areas, baseline_metrics

    def calculate_minimum_feasible_water(
        self,
        total_land_ha: float,
        selected_crops: List[str],
        predicted_water_demands: Dict[str, float],
    ) -> float:
        """Calculate the absolute minimum possible water consumption across all hard-feasible allocations.

        Solves a minimal sub-LP: min sum(x_i * W_i) s.t. sum(x_i) == total_land, min_i <= x_i <= max_i.
        """
        sub_solver = pywraplp.Solver.CreateSolver("GLOP")
        if not sub_solver:
            return 0.0

        x = {}
        for c in selected_crops:
            min_ha = float(self.crops_df.loc[c, "min_land_share"]) * total_land_ha
            max_ha = float(self.crops_df.loc[c, "max_land_share"]) * total_land_ha
            x[c] = sub_solver.NumVar(min_ha, max_ha, f"x_{c}")

        sub_solver.Add(sum(x[c] for c in selected_crops) == total_land_ha)
        sub_solver.Minimize(sum(x[c] * predicted_water_demands[c] for c in selected_crops))
        status = sub_solver.Solve()

        if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return float(sub_solver.Objective().Value())
        return 0.0

    def calculate_maximum_feasible_food(
        self,
        total_land_ha: float,
        selected_crops: List[str],
        predicted_food_coeffs: Dict[str, float],
    ) -> float:
        """Calculate the absolute maximum possible food caloric production across all hard-feasible allocations."""
        sub_solver = pywraplp.Solver.CreateSolver("GLOP")
        if not sub_solver:
            return 0.0

        x = {}
        for c in selected_crops:
            min_ha = float(self.crops_df.loc[c, "min_land_share"]) * total_land_ha
            max_ha = float(self.crops_df.loc[c, "max_land_share"]) * total_land_ha
            x[c] = sub_solver.NumVar(min_ha, max_ha, f"x_{c}")

        sub_solver.Add(sum(x[c] for c in selected_crops) == total_land_ha)
        sub_solver.Maximize(sum(x[c] * predicted_food_coeffs[c] for c in selected_crops))
        status = sub_solver.Solve()

        if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return float(sub_solver.Objective().Value())
        return 0.0

    def calculate_maximum_feasible_income(
        self,
        total_land_ha: float,
        selected_crops: List[str],
        predicted_income_coeffs: Dict[str, float],
    ) -> float:
        """Calculate the absolute maximum possible net income across all hard-feasible allocations."""
        sub_solver = pywraplp.Solver.CreateSolver("GLOP")
        if not sub_solver:
            return 0.0

        x = {}
        for c in selected_crops:
            min_ha = float(self.crops_df.loc[c, "min_land_share"]) * total_land_ha
            max_ha = float(self.crops_df.loc[c, "max_land_share"]) * total_land_ha
            x[c] = sub_solver.NumVar(min_ha, max_ha, f"x_{c}")

        sub_solver.Add(sum(x[c] for c in selected_crops) == total_land_ha)
        sub_solver.Maximize(sum(x[c] * predicted_income_coeffs[c] for c in selected_crops))
        status = sub_solver.Solve()

        if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return float(sub_solver.Objective().Value())
        return 0.0

    def optimize(self, request: OptimizationRequest) -> OptimizationResponse:
        """Execute deterministic crop allocation optimization.

        Args:
            request: OptimizationRequest configuration.

        Returns:
            Structured OptimizationResponse.

        Raises:
            OptimizationValidationException: If hard constraints cannot be satisfied.
        """
        start_time = time.perf_counter()

        total_land_ha = float(request.total_land_ha)
        selected_crops = [c.lower() for c in (request.selected_crops or self.all_crops)]

        # 1. Validate hard constraints
        self.validate_hard_constraints(total_land_ha, selected_crops)

        # 2. Determine weather & water availability ratio
        rainfall_scenario = request.rainfall_scenario.lower()

        # Compute baseline under normal climate first for reference targets
        _, ref_baseline = self.calculate_baseline(
            total_land_ha=total_land_ha,
            rainfall_scenario="normal",
            water_availability_ratio=1.0,
            selected_crops=selected_crops,
        )

        # Resolve scenario water availability ratio
        if request.water_availability_ratio is not None:
            water_avail_ratio = float(request.water_availability_ratio)
        elif request.water_budget_reduction_pct is not None:
            water_avail_ratio = max(0.05, 1.0 - (float(request.water_budget_reduction_pct) / 100.0))
        elif request.water_budget_m3 is not None and ref_baseline["total_water_use_m3"] > 0:
            water_avail_ratio = min(2.0, max(0.05, float(request.water_budget_m3) / ref_baseline["total_water_use_m3"]))
        else:
            water_avail_ratio = 1.0

        # Resolve targets
        # Water budget:
        if request.water_budget_m3 is not None:
            water_budget_m3 = float(request.water_budget_m3)
        elif request.water_budget_reduction_pct is not None:
            reduction = float(request.water_budget_reduction_pct) / 100.0
            water_budget_m3 = max(0.0, ref_baseline["total_water_use_m3"] * (1.0 - reduction))
        else:
            water_budget_m3 = float(ref_baseline["total_water_use_m3"])

        # Food target:
        if request.food_target_kcal is not None:
            food_target_kcal = float(request.food_target_kcal)
        elif request.food_target_increase_pct is not None:
            inc = float(request.food_target_increase_pct) / 100.0
            food_target_kcal = max(0.0, ref_baseline["total_food_kcal"] * (1.0 + inc))
        else:
            food_target_kcal = float(ref_baseline["total_food_kcal"])

        # Income target:
        if request.income_target_inr is not None:
            income_target_inr = float(request.income_target_inr)
        elif request.income_target_increase_pct is not None:
            inc = float(request.income_target_increase_pct) / 100.0
            income_target_inr = ref_baseline["total_net_income_inr"] * (1.0 + inc)
        else:
            income_target_inr = float(ref_baseline["total_net_income_inr"])

        # 3. Predict yields and seasonal irrigation requirements
        crop_predictions = self.predictor.predict_all_crops(
            rainfall_scenario=rainfall_scenario,
            water_availability_ratio=water_avail_ratio,
            crops=selected_crops,
        ).predictions

        # Calculate scenario-specific baseline for side-by-side comparison
        _, scenario_baseline = self.calculate_baseline(
            total_land_ha=total_land_ha,
            rainfall_scenario=rainfall_scenario,
            water_availability_ratio=water_avail_ratio,
            selected_crops=selected_crops,
        )

        # 4. Coefficients per hectare
        # x_i: area in ha
        # water_coeff: m3 / ha
        # food_coeff: kcal / ha = Y_i * 1000 * cal_kg
        # net_income_coeff: INR / ha = 10 * Y_i * price_q - cost_ha
        water_coeffs: Dict[str, float] = {}
        food_coeffs: Dict[str, float] = {}
        income_coeffs: Dict[str, float] = {}
        revenue_coeffs: Dict[str, float] = {}
        cost_coeffs: Dict[str, float] = {}

        for c in selected_crops:
            pred = crop_predictions[c]
            y = pred.predicted_yield_t_ha
            w = pred.predicted_water_demand_m3_ha
            price = float(self.crops_df.loc[c, "price_inr_quintal"])
            cost = float(self.crops_df.loc[c, "cultivation_cost_inr_ha"])
            cal = float(self.crops_df.loc[c, "calories_kcal_kg"])

            rev_ha = 10.0 * y * price
            net_ha = rev_ha - cost

            water_coeffs[c] = w
            food_coeffs[c] = y * 1000.0 * cal
            income_coeffs[c] = net_ha
            revenue_coeffs[c] = rev_ha
            cost_coeffs[c] = cost

        # Compute physical bounds across all legal crop allocations
        min_feasible_water = self.calculate_minimum_feasible_water(
            total_land_ha=total_land_ha,
            selected_crops=selected_crops,
            predicted_water_demands=water_coeffs,
        )
        max_feasible_food = self.calculate_maximum_feasible_food(
            total_land_ha=total_land_ha,
            selected_crops=selected_crops,
            predicted_food_coeffs=food_coeffs,
        )
        max_feasible_income = self.calculate_maximum_feasible_income(
            total_land_ha=total_land_ha,
            selected_crops=selected_crops,
            predicted_income_coeffs=income_coeffs,
        )

        # 5. Normalization scales (positive scales for dimensional consistency)
        scale_w = max(water_budget_m3, ref_baseline["total_water_use_m3"], 1.0)
        scale_f = max(food_target_kcal, ref_baseline["total_food_kcal"], 1.0)
        scale_i = max(income_target_inr, ref_baseline["total_net_income_inr"], 1.0)

        # 6. Initialize OR-Tools GLOP Linear Solver
        solver = pywraplp.Solver.CreateSolver("GLOP")
        if not solver:
            raise RuntimeError("Failed to create OR-Tools GLOP linear solver instance.")

        # Decision variables: crop allocation x_c in hectares
        x: Dict[str, pywraplp.Variable] = {}
        for c in selected_crops:
            min_ha = float(self.crops_df.loc[c, "min_land_share"]) * total_land_ha
            max_ha = float(self.crops_df.loc[c, "max_land_share"]) * total_land_ha
            x[c] = solver.NumVar(min_ha, max_ha, f"x_{c}")

        # Hard land conservation constraint: sum(x_c) == total_land_ha
        land_constraint = solver.Add(
            sum(x[c] for c in selected_crops) == total_land_ha,
            "land_conservation",
        )

        # Soft slack variables (nonnegative)
        s_w = solver.NumVar(0.0, solver.infinity(), "water_slack")
        s_f = solver.NumVar(0.0, solver.infinity(), "food_slack")
        s_i = solver.NumVar(0.0, solver.infinity(), "income_slack")

        # Soft constraints
        # Total water use - s_w <= water_budget
        water_expr = sum(x[c] * water_coeffs[c] for c in selected_crops)
        water_constraint = solver.Add(
            water_expr - s_w <= water_budget_m3,
            "soft_water_budget",
        )

        # Total food energy + s_f >= food_target
        food_expr = sum(x[c] * food_coeffs[c] for c in selected_crops)
        food_constraint = solver.Add(
            food_expr + s_f >= food_target_kcal,
            "soft_food_target",
        )

        # Total net income + s_i >= income_target
        income_expr = sum(x[c] * income_coeffs[c] for c in selected_crops)
        income_constraint = solver.Add(
            income_expr + s_i >= income_target_inr,
            "soft_income_target",
        )

        # Small water tie-breaker: 1e-5 * (water_use / scale_w)
        # Prevents arbitrary crop shifting when targets are equally satisfied
        water_tie_breaker = 1e-5 * (water_expr / scale_w)

        # 7. Execute Optimization Mode
        mode = request.optimization_mode
        weights = request.weights or OptimizationWeights()

        if request.water_first_priority and mode == OptimizationMode.WEIGHTED:
            # Water-first priority boosts water weight
            w_w, w_f, w_i = 0.80, 0.10, 0.10
        else:
            total_w = weights.water + weights.food + weights.income
            w_w = weights.water / total_w
            w_f = weights.food / total_w
            w_i = weights.income / total_w

        if mode == OptimizationMode.LEXICOGRAPHIC:
            # Lexicographic Priority: Water -> Food -> Income
            # Phase 1: Minimize water shortfall
            solver.Minimize((s_w / scale_w) + 1e-6 * (water_expr / scale_w))
            solver.Solve()
            opt_sw = s_w.solution_value()

            # Preserve water slack within strict numerical tolerance (1e-4)
            tol_w = max(1e-4, 1e-4 * opt_sw)
            solver.Add(s_w <= opt_sw + tol_w, "lex_water_preserve")

            # Phase 2: Minimize food shortfall
            solver.Minimize(s_f / scale_f)
            solver.Solve()
            opt_sf = s_f.solution_value()

            # Preserve food slack within strict numerical tolerance (1e-4)
            tol_f = max(1e-4, 1e-4 * opt_sf)
            solver.Add(s_f <= opt_sf + tol_f, "lex_food_preserve")

            # Phase 3: Minimize income shortfall + water tie-breaker
            solver.Minimize((s_i / scale_i) + water_tie_breaker)
            status = solver.Solve()

        else:
            # Weighted Mode: Minimize weighted normalized shortfalls + tie-breaker
            objective = (
                w_w * (s_w / scale_w)
                + w_f * (s_f / scale_f)
                + w_i * (s_i / scale_i)
                + water_tie_breaker
            )
            solver.Minimize(objective)
            status = solver.Solve()

        solve_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            # This should never occur when hard constraints are valid due to non-negative slacks
            raise RuntimeError(
                f"Unexpected solver failure (status {status}). Check system numerical stability."
            )

        solver_status_str = "OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE"

        # 8. Extract Solution Decision Variables
        allocations: List[CropAllocationResult] = []
        tot_water = 0.0
        tot_food = 0.0
        tot_rev = 0.0
        tot_cost = 0.0

        # Round areas to 3 decimals and preserve exact land conservation
        raw_areas = {c: max(0.0, float(x[c].solution_value())) for c in selected_crops}
        rounded_areas = {c: round(raw_areas[c], 3) for c in selected_crops}
        residual = round(total_land_ha - sum(rounded_areas.values()), 3)
        if abs(residual) > 1e-6 and len(rounded_areas) > 0:
            max_c = max(rounded_areas.keys(), key=lambda k: rounded_areas[k])
            rounded_areas[max_c] = round(rounded_areas[max_c] + residual, 3)

        for c in selected_crops:
            area = rounded_areas[c]
            land_pct = (area / total_land_ha) * 100.0 if total_land_ha > 0 else 0.0

            pred = crop_predictions[c]
            y = pred.predicted_yield_t_ha
            w = pred.predicted_water_demand_m3_ha
            price = float(self.crops_df.loc[c, "price_inr_quintal"])
            cost_ha = float(self.crops_df.loc[c, "cultivation_cost_inr_ha"])
            cal = float(self.crops_df.loc[c, "calories_kcal_kg"])

            prod_tonnes = round(area * y, 3)
            prod_quintals = round(prod_tonnes * 10.0, 2)
            gross_rev = round(prod_quintals * price, 1)
            c_cost = round(area * cost_ha, 1)
            net_inc = round(gross_rev - c_cost, 1)
            c_food = round(prod_tonnes * 1000.0 * cal, 1)
            c_water = round(area * w, 1)

            tot_water += c_water
            tot_food += c_food
            tot_rev += gross_rev
            tot_cost += c_cost

            allocations.append(
                CropAllocationResult(
                    crop_id=c,
                    crop_name=str(self.crops_df.loc[c, "crop_name"]),
                    allocated_ha=area,
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

        tot_net_income = round(tot_rev - tot_cost, 1)
        tot_water = round(tot_water, 1)
        tot_food = round(tot_food, 1)
        tot_rev = round(tot_rev, 1)
        tot_cost = round(tot_cost, 1)

        # Reconcile slacks: if solver satisfied constraint (slack < 1e-4), report 0.0.
        # Otherwise, report actual shortfall.
        val_sw = 0.0 if s_w.solution_value() < 1e-4 else round(max(0.0, tot_water - water_budget_m3), 1)
        val_sf = 0.0 if s_f.solution_value() < 1e-4 else round(max(0.0, food_target_kcal - tot_food), 1)
        val_si = 0.0 if s_i.solution_value() < 1e-4 else round(max(0.0, income_target_inr - tot_net_income), 1)

        water_shortfall_pct = (val_sw / water_budget_m3 * 100.0) if water_budget_m3 > 0 else 0.0
        food_shortfall_pct = (val_sf / food_target_kcal * 100.0) if food_target_kcal > 0 else 0.0
        income_shortfall_pct = (val_si / income_target_inr * 100.0) if income_target_inr > 0 else 0.0

        # 9. Extract Binding Constraints and GLOP Dual Values
        binding_constraints: List[BindingConstraint] = []
        tol = 1e-4

        # Land constraint
        land_dual = float(land_constraint.dual_value())
        binding_constraints.append(
            BindingConstraint(
                name="land_conservation",
                constraint_type="hard_land",
                limit_value=total_land_ha,
                achieved_value=round(sum(a.allocated_ha for a in allocations), 3),
                is_binding=True,
                dual_value=round(land_dual, 6),
                sensitivity_label="local_model_sensitivity",
                interpretation=(
                    f"Marginal objective sensitivity to available land area (dual = {land_dual:.6f}). "
                    "Reflects local mathematical derivative in linear program, not a market land rent."
                ),
            )
        )

        # Soft water budget constraint
        water_dual = float(water_constraint.dual_value())
        is_water_binding = (val_sw > tol) or (abs(tot_water - water_budget_m3) < 1.0)
        binding_constraints.append(
            BindingConstraint(
                name="soft_water_budget",
                constraint_type="soft_water",
                limit_value=round(water_budget_m3, 1),
                achieved_value=round(tot_water, 1),
                is_binding=is_water_binding,
                dual_value=round(water_dual, 6),
                sensitivity_label="local_model_sensitivity",
                interpretation=(
                    f"Marginal objective sensitivity to water budget relaxation (dual = {water_dual:.6f}). "
                    "Represents local model derivative, not an economic water tariff."
                ),
            )
        )

        # Soft food target constraint
        food_dual = float(food_constraint.dual_value())
        is_food_binding = (val_sf > tol) or (abs(tot_food - food_target_kcal) < 1000.0)
        binding_constraints.append(
            BindingConstraint(
                name="soft_food_target",
                constraint_type="soft_food",
                limit_value=round(food_target_kcal, 1),
                achieved_value=round(tot_food, 1),
                is_binding=is_food_binding,
                dual_value=round(food_dual, 8),
                sensitivity_label="local_model_sensitivity",
                interpretation=f"Marginal objective sensitivity to food target (dual = {food_dual:.8f}).",
            )
        )

        # Soft income target constraint
        income_dual = float(income_constraint.dual_value())
        is_income_binding = (val_si > tol) or (abs(tot_net_income - income_target_inr) < 1.0)
        binding_constraints.append(
            BindingConstraint(
                name="soft_income_target",
                constraint_type="soft_income",
                limit_value=round(income_target_inr, 1),
                achieved_value=round(tot_net_income, 1),
                is_binding=is_income_binding,
                dual_value=round(income_dual, 6),
                sensitivity_label="local_model_sensitivity",
                interpretation=f"Marginal objective sensitivity to income target (dual = {income_dual:.6f}).",
            )
        )

        # Crop bound constraints
        for a in allocations:
            c = a.crop_id
            min_ha = float(self.crops_df.loc[c, "min_land_share"]) * total_land_ha
            max_ha = float(self.crops_df.loc[c, "max_land_share"]) * total_land_ha

            if abs(a.allocated_ha - max_ha) < tol:
                binding_constraints.append(
                    BindingConstraint(
                        name=f"crop_max_share_{c}",
                        constraint_type="hard_crop_max",
                        limit_value=round(max_ha, 3),
                        achieved_value=a.allocated_ha,
                        is_binding=True,
                        dual_value=None,
                        interpretation=f"Crop '{c}' reached its maximum agronomic rotation ceiling of {max_ha:.2f} ha.",
                    )
                )
            elif abs(a.allocated_ha - min_ha) < tol and min_ha > 0:
                binding_constraints.append(
                    BindingConstraint(
                        name=f"crop_min_share_{c}",
                        constraint_type="hard_crop_min",
                        limit_value=round(min_ha, 3),
                        achieved_value=a.allocated_ha,
                        is_binding=True,
                        dual_value=None,
                        interpretation=f"Crop '{c}' restricted by its minimum agronomic floor of {min_ha:.2f} ha.",
                    )
                )

        # 10. Construct Local Model Sensitivities
        local_sensitivities: List[LocalModelSensitivity] = [
            LocalModelSensitivity(
                parameter_name="water_budget_m3",
                marginal_value=round(abs(water_dual), 6),
                unit="objective_units_per_m3",
                interpretation=(
                    "An additional 1 m³ of water budget relaxes the objective by "
                    f"{abs(water_dual):.6f} normalized objective units. "
                    "Labeled as local model sensitivity, NOT a market water tariff."
                ),
            ),
            LocalModelSensitivity(
                parameter_name="total_land_ha",
                marginal_value=round(abs(land_dual), 6),
                unit="objective_units_per_ha",
                interpretation=(
                    f"An additional 1 hectare of land shifts the objective by {abs(land_dual):.6f} units. "
                    "Labeled as local model sensitivity within the linear solver."
                ),
            ),
        ]

        # 11. Baseline Comparison (Side-by-side KPI cards)
        # Compare against the scenario baseline
        b_water = scenario_baseline["total_water_use_m3"]
        b_food = scenario_baseline["total_food_kcal"]
        b_inc = scenario_baseline["total_net_income_inr"]

        delta_w = tot_water - b_water
        pct_w = (delta_w / b_water * 100.0) if b_water > 0 else 0.0

        delta_f = tot_food - b_food
        pct_f = (delta_f / b_food * 100.0) if b_food > 0 else 0.0

        delta_i = tot_net_income - b_inc
        pct_i = (delta_i / abs(b_inc) * 100.0) if abs(b_inc) > 0 else 0.0

        # Status criteria:
        # Water: green if <= budget, amber if gap <= 20%, red if gap > 20%
        if val_sw <= tol:
            status_w = "green"
        elif water_shortfall_pct <= 20.0:
            status_w = "amber"
        else:
            status_w = "red"

        # Food: green if >= target, amber if shortfall <= 20%, red if > 20%
        if val_sf <= tol:
            status_f = "green"
        elif food_shortfall_pct <= 20.0:
            status_f = "amber"
        else:
            status_f = "red"

        # Income: green if >= target, amber if shortfall <= 20%, red if > 20%
        if val_si <= tol:
            status_i = "green"
        elif income_shortfall_pct <= 20.0:
            status_i = "amber"
        else:
            status_i = "red"

        baseline_comparison: Dict[str, MetricComparison] = {
            "water": MetricComparison(
                metric_name="Irrigation Water Use",
                unit="m³",
                baseline_value=round(b_water, 1),
                optimized_value=round(tot_water, 1),
                delta_value=round(delta_w, 1),
                delta_percentage=round(pct_w, 1),
                target_value=round(water_budget_m3, 1),
                shortfall=round(val_sw, 1),
                status=status_w,
            ),
            "food": MetricComparison(
                metric_name="Food Energy Production",
                unit="kcal",
                baseline_value=round(b_food, 1),
                optimized_value=round(tot_food, 1),
                delta_value=round(delta_f, 1),
                delta_percentage=round(pct_f, 1),
                target_value=round(food_target_kcal, 1),
                shortfall=round(val_sf, 1),
                status=status_f,
            ),
            "income": MetricComparison(
                metric_name="Farmer Net Income",
                unit="₹",
                baseline_value=round(b_inc, 1),
                optimized_value=round(tot_net_income, 1),
                delta_value=round(delta_i, 1),
                delta_percentage=round(pct_i, 1),
                target_value=round(income_target_inr, 1),
                shortfall=round(val_si, 1),
                status=status_i,
            ),
        }

        # 12. Bottleneck Diagnosis
        diagnosis = AquaShiftDiagnostician.diagnose(
            allocations=allocations,
            water_achieved_m3=tot_water,
            water_budget_m3=water_budget_m3,
            water_slack_m3=val_sw,
            food_achieved_kcal=tot_food,
            food_target_kcal=food_target_kcal,
            food_slack_kcal=val_sf,
            income_achieved_inr=tot_net_income,
            income_target_inr=income_target_inr,
            income_slack_inr=val_si,
            min_feasible_water_m3=min_feasible_water,
            binding_constraints=binding_constraints,
            max_feasible_food_kcal=max_feasible_food,
            max_feasible_income_inr=max_feasible_income,
        )

        return OptimizationResponse(
            solver_status=solver_status_str,
            optimization_mode=mode.value if isinstance(mode, OptimizationMode) else str(mode),
            total_land_ha=round(total_land_ha, 3),
            allocations=allocations,
            total_water_use_m3=round(tot_water, 1),
            water_budget_m3=round(water_budget_m3, 1),
            water_slack_m3=round(val_sw, 1),
            water_shortfall_pct=round(water_shortfall_pct, 1),
            total_food_kcal=round(tot_food, 1),
            food_target_kcal=round(food_target_kcal, 1),
            food_slack_kcal=round(val_sf, 1),
            food_shortfall_pct=round(food_shortfall_pct, 1),
            total_gross_revenue_inr=round(tot_rev, 1),
            total_cultivation_cost_inr=round(tot_cost, 1),
            total_net_income_inr=round(tot_net_income, 1),
            income_target_inr=round(income_target_inr, 1),
            income_slack_inr=round(val_si, 1),
            income_shortfall_pct=round(income_shortfall_pct, 1),
            binding_constraints=binding_constraints,
            local_sensitivities=local_sensitivities,
            baseline_comparison=baseline_comparison,
            diagnosis=diagnosis,
            objective_value=round(float(solver.Objective().Value()), 6),
            solve_time_ms=solve_time_ms,
        )
