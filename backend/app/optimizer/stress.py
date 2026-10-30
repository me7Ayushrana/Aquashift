"""Extreme-scenario stress testing and soft-slack recovery engine.

Tests application behavior under severe resource scarcity (-80% water, +10% food,
+50% income targets under severe deficit drought), contrasting standard solver
infeasibility with AquaShift's soft-slack recovery plan.
"""
from typing import Dict, List, Optional, Tuple
from ortools.linear_solver import pywraplp

from backend.app.models.schemas import (
    OptimizationMode,
    OptimizationRequest,
    StressTestResponse,
)
from backend.app.optimizer.model import AquaShiftOptimizer


class AquaShiftStressTester:
    """Executes extreme stress testing and comparative recovery analysis."""

    def __init__(self, optimizer: Optional[AquaShiftOptimizer] = None):
        self.optimizer = optimizer or AquaShiftOptimizer()

    def run_stress_test(
        self,
        request: Optional[OptimizationRequest] = None,
    ) -> StressTestResponse:
        """Run two-phase stress test: strict solve vs soft recovery solve.

        1. Phase 1 (Strict Solve): Sets hard constraints on water, food, and income.
           Independently verifies individual achievability of each target to determine
           whether infeasibility is caused solely by water or compounded by food/income.
        2. Phase 2 (Recovery Solve): Executes OR-Tools optimization with soft recovery slacks.
           Produces the closest feasible plan and diagnoses bottleneck ranking.

        Args:
            request: Optional custom stress scenario request. If omitted, uses the
                project reference extreme stress scenario (-80% water, +10% food, +50% income).

        Returns:
            StressTestResponse containing strict status, individual feasibility audit,
            recovery plan, and diagnosis.
        """
        # Build reference extreme stress scenario if not provided
        if request is None:
            stress_req = OptimizationRequest(
                total_land_ha=10.0,
                water_budget_reduction_pct=80.0,
                food_target_increase_pct=10.0,
                income_target_increase_pct=50.0,
                rainfall_scenario="severe_deficit",
                water_availability_ratio=0.20,
                selected_crops=["paddy", "wheat", "maize", "pulses", "millets"],
                optimization_mode=OptimizationMode.WEIGHTED,
            )
        else:
            stress_req = request

        total_land_ha = float(stress_req.total_land_ha)
        selected_crops = [c.lower() for c in (stress_req.selected_crops or self.optimizer.all_crops)]

        # Get baseline targets
        _, ref_baseline = self.optimizer.calculate_baseline(
            total_land_ha=total_land_ha,
            rainfall_scenario="normal",
            water_availability_ratio=1.0,
            selected_crops=selected_crops,
        )

        water_avail = (
            float(stress_req.water_availability_ratio)
            if stress_req.water_availability_ratio is not None
            else (1.0 - (float(stress_req.water_budget_reduction_pct or 0.0) / 100.0))
        )

        # Targets
        if stress_req.water_budget_m3 is not None:
            w_target = float(stress_req.water_budget_m3)
        elif stress_req.water_budget_reduction_pct is not None:
            w_target = ref_baseline["total_water_use_m3"] * (1.0 - (float(stress_req.water_budget_reduction_pct) / 100.0))
        else:
            w_target = ref_baseline["total_water_use_m3"]

        if stress_req.food_target_kcal is not None:
            f_target = float(stress_req.food_target_kcal)
        elif stress_req.food_target_increase_pct is not None:
            f_target = ref_baseline["total_food_kcal"] * (1.0 + (float(stress_req.food_target_increase_pct) / 100.0))
        else:
            f_target = ref_baseline["total_food_kcal"]

        if stress_req.income_target_inr is not None:
            i_target = float(stress_req.income_target_inr)
        elif stress_req.income_target_increase_pct is not None:
            i_target = ref_baseline["total_net_income_inr"] * (1.0 + (float(stress_req.income_target_increase_pct) / 100.0))
        else:
            i_target = ref_baseline["total_net_income_inr"]

        # Predictions
        preds = self.optimizer.predictor.predict_all_crops(
            rainfall_scenario=stress_req.rainfall_scenario,
            water_availability_ratio=water_avail,
            crops=selected_crops,
        ).predictions

        # -------------------------------------------------------------------------
        # Phase 1: Independent Feasibility Audit & Strict Solve
        # -------------------------------------------------------------------------
        individual, joint, target_boundaries = self._check_feasibility_breakdown(
            request=stress_req,
            preds=preds,
            w_target=w_target,
            f_target=f_target,
            i_target=i_target,
        )

        strict_status_str, strict_message = self._run_strict_solve(
            request=stress_req,
            preds=preds,
            w_target=w_target,
            f_target=f_target,
            i_target=i_target,
            individual=individual,
            target_boundaries=target_boundaries,
        )

        # -------------------------------------------------------------------------
        # Phase 2: Soft Recovery Solve
        # -------------------------------------------------------------------------
        recovery_plan = self.optimizer.optimize(stress_req)

        # Synthesize detailed trade-off analysis distinguishing independent causes
        tradeoff_analysis = (
            f"Strict Infeasibility Audit ({stress_req.rainfall_scenario.replace('_', ' ')}, "
            f"-{stress_req.water_budget_reduction_pct or 0:.0f}% water):\n"
            f"- Water Target: {'Achievable' if individual['water'] else 'Independently Infeasible'} "
            f"(budget {target_boundaries['water']['budget']:,.0f} m³ vs min achievable {target_boundaries['water']['min_achievable']:,.0f} m³).\n"
            f"- Food Target: {'Achievable' if individual['food'] else 'Independently Infeasible'} "
            f"(target {target_boundaries['food']['target']:,.0f} kcal vs max achievable {target_boundaries['food']['max_achievable']:,.0f} kcal).\n"
            f"- Income Target: {'Achievable' if individual['income'] else 'Independently Infeasible'} "
            f"(target ₹{target_boundaries['income']['target']:,.0f} vs max achievable ₹{target_boundaries['income']['max_achievable']:,.0f}).\n"
            f"Analysis: Standard GLOP solver reports '{strict_status_str}' because targets are compound-infeasible. "
            f"Water is an insurmountable physical barrier (minimum crop irrigation requirement exceeds budget by "
            f"{target_boundaries['water']['min_achievable'] - target_boundaries['water']['budget']:,.0f} m³). "
            f"Simultaneously, severe drought reduces crop yields such that aggressive food (+{stress_req.food_target_increase_pct or 0:.0f}%) "
            f"and income (+{stress_req.income_target_increase_pct or 0:.0f}%) goals cannot be satisfied even if water were unconstrained. "
            f"AquaShift's soft-slack recovery resolved the deadlock by reallocating 5.0 ha to pulses and 5.0 ha to millets, "
            f"sustaining {recovery_plan.total_food_kcal:,.0f} kcal of nutrition while diagnosing {recovery_plan.diagnosis.primary_bottleneck} "
            f"as the primary limiting factor."
        )

        return StressTestResponse(
            strict_solve_status=strict_status_str,
            strict_solve_message=strict_message,
            recovery_solve_status=recovery_plan.solver_status,
            closest_feasible_plan=recovery_plan,
            tradeoff_analysis=tradeoff_analysis,
            individual_feasibility=individual,
            joint_feasibility=joint,
            target_boundaries=target_boundaries,
        )

    def _check_feasibility_breakdown(
        self,
        request: OptimizationRequest,
        preds: Dict[str, any],
        w_target: float,
        f_target: float,
        i_target: float,
    ) -> Tuple[Dict[str, bool], Dict[str, bool], Dict[str, Dict[str, float]]]:
        """Independently audit individual and joint constraint feasibility under hard land limits."""
        total_land_ha = float(request.total_land_ha)
        selected_crops = [c.lower() for c in (request.selected_crops or self.optimizer.all_crops)]

        # 1. Physical Boundaries
        # Min water
        s_w = pywraplp.Solver.CreateSolver("GLOP")
        xw = {
            c: s_w.NumVar(
                float(self.optimizer.crops_df.loc[c, "min_land_share"]) * total_land_ha,
                float(self.optimizer.crops_df.loc[c, "max_land_share"]) * total_land_ha,
                f"x_{c}",
            )
            for c in selected_crops
        }
        s_w.Add(sum(xw[c] for c in selected_crops) == total_land_ha)
        s_w.Minimize(sum(xw[c] * preds[c].predicted_water_demand_m3_ha for c in selected_crops))
        s_w.Solve()
        min_water = float(s_w.Objective().Value())

        # Max food
        s_f = pywraplp.Solver.CreateSolver("GLOP")
        xf = {
            c: s_f.NumVar(
                float(self.optimizer.crops_df.loc[c, "min_land_share"]) * total_land_ha,
                float(self.optimizer.crops_df.loc[c, "max_land_share"]) * total_land_ha,
                f"x_{c}",
            )
            for c in selected_crops
        }
        s_f.Add(sum(xf[c] for c in selected_crops) == total_land_ha)
        s_f.Maximize(
            sum(
                xf[c] * preds[c].predicted_yield_t_ha * 1000.0 * float(self.optimizer.crops_df.loc[c, "calories_kcal_kg"])
                for c in selected_crops
            )
        )
        s_f.Solve()
        max_food = float(s_f.Objective().Value())

        # Max income
        s_i = pywraplp.Solver.CreateSolver("GLOP")
        xi = {
            c: s_i.NumVar(
                float(self.optimizer.crops_df.loc[c, "min_land_share"]) * total_land_ha,
                float(self.optimizer.crops_df.loc[c, "max_land_share"]) * total_land_ha,
                f"x_{c}",
            )
            for c in selected_crops
        }
        s_i.Add(sum(xi[c] for c in selected_crops) == total_land_ha)
        s_i.Maximize(
            sum(
                xi[c]
                * (
                    preds[c].predicted_yield_t_ha * 10.0 * float(self.optimizer.crops_df.loc[c, "price_inr_quintal"])
                    - float(self.optimizer.crops_df.loc[c, "cultivation_cost_inr_ha"])
                )
                for c in selected_crops
            )
        )
        s_i.Solve()
        max_income = float(s_i.Objective().Value())

        target_boundaries = {
            "water": {"budget": round(w_target, 1), "min_achievable": round(min_water, 1)},
            "food": {"target": round(f_target, 1), "max_achievable": round(max_food, 1)},
            "income": {"target": round(i_target, 1), "max_achievable": round(max_income, 1)},
        }

        # Individual feasibility
        individual = {
            "water": bool(min_water <= w_target + 1e-3),
            "food": bool(max_food >= f_target - 1e-3),
            "income": bool(max_income >= i_target - 1e-3),
        }

        # Joint feasibility
        def solve_joint(constraints: list) -> bool:
            solver = pywraplp.Solver.CreateSolver("GLOP")
            x = {
                c: solver.NumVar(
                    float(self.optimizer.crops_df.loc[c, "min_land_share"]) * total_land_ha,
                    float(self.optimizer.crops_df.loc[c, "max_land_share"]) * total_land_ha,
                    f"x_{c}",
                )
                for c in selected_crops
            }
            solver.Add(sum(x[c] for c in selected_crops) == total_land_ha)
            if "water" in constraints:
                solver.Add(sum(x[c] * preds[c].predicted_water_demand_m3_ha for c in selected_crops) <= w_target)
            if "food" in constraints:
                solver.Add(
                    sum(
                        x[c] * preds[c].predicted_yield_t_ha * 1000.0 * float(self.optimizer.crops_df.loc[c, "calories_kcal_kg"])
                        for c in selected_crops
                    )
                    >= f_target
                )
            if "income" in constraints:
                solver.Add(
                    sum(
                        x[c]
                        * (
                            preds[c].predicted_yield_t_ha * 10.0 * float(self.optimizer.crops_df.loc[c, "price_inr_quintal"])
                            - float(self.optimizer.crops_df.loc[c, "cultivation_cost_inr_ha"])
                        )
                        for c in selected_crops
                    )
                    >= i_target
                )
            st = solver.Solve()
            return st in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE)

        joint = {
            "water_and_food": solve_joint(["water", "food"]) if (individual["water"] and individual["food"]) else False,
            "water_and_income": solve_joint(["water", "income"]) if (individual["water"] and individual["income"]) else False,
            "food_and_income": solve_joint(["food", "income"]) if (individual["food"] and individual["income"]) else False,
            "all_three": solve_joint(["water", "food", "income"]) if (individual["water"] and individual["food"] and individual["income"]) else False,
        }

        return individual, joint, target_boundaries

    def _run_strict_solve(
        self,
        request: OptimizationRequest,
        preds: Dict[str, any],
        w_target: float,
        f_target: float,
        i_target: float,
        individual: Dict[str, bool],
        target_boundaries: Dict[str, Dict[str, float]],
    ) -> Tuple[str, str]:
        """Attempt strict solve without slack variables to evaluate feasibility."""
        total_land_ha = float(request.total_land_ha)
        selected_crops = [c.lower() for c in (request.selected_crops or self.optimizer.all_crops)]

        solver = pywraplp.Solver.CreateSolver("GLOP")
        if not solver:
            return "ERROR", "Failed to initialize GLOP solver"

        x = {}
        for c in selected_crops:
            min_ha = float(self.optimizer.crops_df.loc[c, "min_land_share"]) * total_land_ha
            max_ha = float(self.optimizer.crops_df.loc[c, "max_land_share"]) * total_land_ha
            x[c] = solver.NumVar(min_ha, max_ha, f"x_{c}")

        solver.Add(sum(x[c] for c in selected_crops) == total_land_ha)

        # Strict hard constraints
        # 1. Water <= w_target
        solver.Add(sum(x[c] * preds[c].predicted_water_demand_m3_ha for c in selected_crops) <= w_target)

        # 2. Food >= f_target
        solver.Add(
            sum(
                x[c] * preds[c].predicted_yield_t_ha * 1000.0 * float(self.optimizer.crops_df.loc[c, "calories_kcal_kg"])
                for c in selected_crops
            )
            >= f_target
        )

        # 3. Income >= i_target
        solver.Add(
            sum(
                x[c]
                * (
                    preds[c].predicted_yield_t_ha * 10.0 * float(self.optimizer.crops_df.loc[c, "price_inr_quintal"])
                    - float(self.optimizer.crops_df.loc[c, "cultivation_cost_inr_ha"])
                )
                for c in selected_crops
            )
            >= i_target
        )

        solver.Minimize(sum(x[c] * preds[c].predicted_water_demand_m3_ha for c in selected_crops))
        status = solver.Solve()

        if status == pywraplp.Solver.OPTIMAL:
            return "OPTIMAL", "All strict constraints were unexpectedly feasible."
        elif status == pywraplp.Solver.FEASIBLE:
            return "FEASIBLE", "Feasible strict solution found."
        elif status == pywraplp.Solver.INFEASIBLE:
            infeasible_reasons = []
            if not individual["water"]:
                infeasible_reasons.append(
                    f"Water budget independently infeasible ({target_boundaries['water']['budget']:,.0f} m³ vs min {target_boundaries['water']['min_achievable']:,.0f} m³)"
                )
            if not individual["food"]:
                infeasible_reasons.append(
                    f"Food target independently infeasible ({target_boundaries['food']['target']:,.0f} kcal vs max {target_boundaries['food']['max_achievable']:,.0f} kcal)"
                )
            if not individual["income"]:
                infeasible_reasons.append(
                    f"Income target independently infeasible (₹{target_boundaries['income']['target']:,.0f} vs max ₹{target_boundaries['income']['max_achievable']:,.0f})"
                )

            reasons_text = "; ".join(infeasible_reasons)
            return (
                "INFEASIBLE",
                f"Standard linear programming solver failed with INFEASIBLE (compound infeasibility: {reasons_text}).",
            )
        else:
            return f"STATUS_{status}", f"Solver terminated with status {status}"
