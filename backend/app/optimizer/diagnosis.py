"""Diagnosis module for analyzing constraint bottlenecks and shortfall severity.

Evaluates optimizer slacks, binding constraints, and physical resource limits
to explain why competing targets cannot be simultaneously met.
"""
from typing import Dict, List, Optional
from backend.app.models.schemas import (
    BindingConstraint,
    BottleneckRanking,
    CropAllocationResult,
    DiagnosisReport,
)


class AquaShiftDiagnostician:
    """Diagnoses optimization bottlenecks, shortfall magnitudes, and resource conflicts."""

    @staticmethod
    def diagnose(
        allocations: List[CropAllocationResult],
        water_achieved_m3: float,
        water_budget_m3: float,
        water_slack_m3: float,
        food_achieved_kcal: float,
        food_target_kcal: float,
        food_slack_kcal: float,
        income_achieved_inr: float,
        income_target_inr: float,
        income_slack_inr: float,
        min_feasible_water_m3: float,
        binding_constraints: List[BindingConstraint],
        max_feasible_food_kcal: Optional[float] = None,
        max_feasible_income_inr: Optional[float] = None,
    ) -> DiagnosisReport:
        """Analyze optimization outcome and generate structured bottleneck diagnosis.

        Mathematical Ranking & Severity Rules:
        - Severity Tiers:
          - Critical (Weight 4): Absolute physical resource boundary violation (e.g. min_feasible_water > budget),
            or water slack >= 30% of budget.
          - High (Weight 3): Economic crisis (income_achieved < 0 or max_feasible_income < 0), or large shortfall >= 40%.
          - Moderate (Weight 2): Noticeable deficit (slack > 0), but farm produces positive output / food sustenance.
          - Satisfied (Weight 1): Shortfall <= 0.
        - Rank Score Formula:
            rank_score = severity_weight * 1000 + (500 if is_physical_barrier else 0) + min(slack_percentage, 100.0)
          Dimensions are sorted by rank_score descending.
        """
        # Determine missed targets
        missed_targets: List[str] = []
        if water_slack_m3 > 0.1:
            missed_targets.append("Water")
        if food_slack_kcal > 1000.0:
            missed_targets.append("Food")
        if income_slack_inr > 1.0:
            missed_targets.append("Income")

        all_targets_met = len(missed_targets) == 0

        # Calculate shortfall percentages
        water_slack_pct = (
            (water_slack_m3 / water_budget_m3 * 100.0) if water_budget_m3 > 0 else 0.0
        )
        food_slack_pct = (
            (food_slack_kcal / food_target_kcal * 100.0) if food_target_kcal > 0 else 0.0
        )
        income_slack_pct = (
            (income_slack_inr / income_target_inr * 100.0) if income_target_inr > 0 else 0.0
        )

        binding_names = [c.name for c in binding_constraints if c.is_binding]

        # -------------------------------------------------------------------------
        # Physical Feasibility Evaluations
        # -------------------------------------------------------------------------
        water_physical_barrier = min_feasible_water_m3 > (water_budget_m3 + 0.1)
        food_physical_barrier = (max_feasible_food_kcal is not None) and (max_feasible_food_kcal < food_target_kcal - 1.0)
        income_physical_barrier = (max_feasible_income_inr is not None) and (max_feasible_income_inr < income_target_inr - 1.0)

        # -------------------------------------------------------------------------
        # Severity Classifications
        # -------------------------------------------------------------------------
        # 1. Water
        if water_slack_m3 <= 0.1:
            water_severity = "Satisfied"
            water_exp = "Seasonal irrigation demand is fully satisfied within the allocated water budget."
        elif water_physical_barrier or water_slack_pct >= 30.0:
            water_severity = "Critical"
            water_exp = (
                f"Physical water deficit of {water_slack_m3:,.0f} m³ ({water_slack_pct:.1f}% over budget). "
                f"Even allocating 100% of available land to the most drought-hardy crops requires "
                f"{min_feasible_water_m3:,.0f} m³, strictly exceeding the available budget of {water_budget_m3:,.0f} m³."
            )
        elif water_slack_pct >= 10.0:
            water_severity = "High"
            water_exp = f"Substantial water deficit of {water_slack_m3:,.0f} m³ ({water_slack_pct:.1f}% over budget)."
        else:
            water_severity = "Moderate"
            water_exp = f"Moderate water deficit of {water_slack_m3:,.0f} m³ ({water_slack_pct:.1f}% over budget)."

        # 2. Income
        if income_slack_inr <= 1.0:
            income_severity = "Satisfied"
            income_exp = "Farmer net income target is fully achieved."
        elif income_achieved_inr < 0 or (max_feasible_income_inr is not None and max_feasible_income_inr < 0):
            income_severity = "High"
            income_exp = (
                f"Severe farm economic loss: net income is negative (₹{income_achieved_inr:,.0f}) "
                f"due to drought-induced yield depression and fixed cultivation costs, missing the "
                f"₹{income_target_inr:,.0f} target by {income_slack_pct:.1f}%."
            )
        elif income_slack_pct >= 40.0:
            income_severity = "High"
            income_exp = (
                f"High income shortfall of ₹{income_slack_inr:,.0f} ({income_slack_pct:.1f}% below target)."
            )
        else:
            income_severity = "Moderate"
            income_exp = f"Moderate income shortfall of ₹{income_slack_inr:,.0f} ({income_slack_pct:.1f}% below target)."

        # 3. Food
        if food_slack_kcal <= 1000.0:
            food_severity = "Satisfied"
            food_exp = "Target nutritional calorie production is fully met."
        elif food_achieved_kcal > 0 and income_achieved_inr < 0:
            # Calorie production remains positive, providing basic sustenance during an economic crisis
            food_severity = "Moderate"
            food_exp = (
                f"Caloric production shortfall of {food_slack_kcal:,.0f} kcal ({food_slack_pct:.1f}% below target). "
                f"While grain output is reduced, basic nutritional sustenance ({food_achieved_kcal:,.0f} kcal) is maintained."
            )
        elif food_slack_pct >= 50.0:
            food_severity = "High"
            food_exp = f"High food caloric shortfall of {food_slack_kcal:,.0f} kcal ({food_slack_pct:.1f}% below target)."
        else:
            food_severity = "Moderate"
            food_exp = f"Moderate food caloric shortfall of {food_slack_kcal:,.0f} kcal ({food_slack_pct:.1f}% below target)."

        # -------------------------------------------------------------------------
        # Derived Mathematical Ranking
        # -------------------------------------------------------------------------
        sev_weight = {
            "Critical": 4,
            "High": 3,
            "Moderate": 2,
            "Satisfied": 1,
        }

        candidates = [
            {
                "dimension": "Water",
                "severity": water_severity,
                "is_physical_barrier": water_physical_barrier,
                "slack_amount": round(water_slack_m3, 1),
                "slack_percentage": round(water_slack_pct, 1),
                "explanation": water_exp,
            },
            {
                "dimension": "Income",
                "severity": income_severity,
                "is_physical_barrier": income_physical_barrier,
                "slack_amount": round(income_slack_inr, 1),
                "slack_percentage": round(income_slack_pct, 1),
                "explanation": income_exp,
            },
            {
                "dimension": "Food",
                "severity": food_severity,
                "is_physical_barrier": food_physical_barrier,
                "slack_amount": round(food_slack_kcal, 1),
                "slack_percentage": round(food_slack_pct, 1),
                "explanation": food_exp,
            },
        ]

        # Calculate exact rank score for each dimension:
        # rank_score = severity_weight * 1000 + (500 if physical_barrier else 0) + min(slack_percentage, 100.0)
        for c in candidates:
            c["rank_score"] = (
                sev_weight[c["severity"]] * 1000
                + (500 if c["is_physical_barrier"] else 0)
                + min(c["slack_percentage"], 100.0)
            )

        # Sort dimensions by rank_score descending
        candidates.sort(key=lambda c: c["rank_score"], reverse=True)

        bottleneck_ranking = [
            BottleneckRanking(
                rank=i + 1,
                dimension=c["dimension"],
                severity=c["severity"],
                slack_amount=c["slack_amount"],
                slack_percentage=c["slack_percentage"],
                explanation=c["explanation"],
            )
            for i, c in enumerate(candidates)
        ]

        primary_bottleneck = bottleneck_ranking[0].dimension if not all_targets_met else None

        # Narrative diagnosis
        if all_targets_met:
            narrative = (
                "All scenario targets (water conservation, food security, and net farm income) "
                "were successfully satisfied without slack. The proposed crop diversification plan "
                "respects all agronomic land limits while maintaining viable returns."
            )
        else:
            reasons = []
            if water_severity in ("Critical", "High"):
                reasons.append(
                    f"Water is a {water_severity.lower()} bottleneck: the available budget of "
                    f"{water_budget_m3:,.0f} m³ is insufficient for full crop evapotranspiration, "
                    f"resulting in a {water_slack_pct:.1f}% shortfall."
                )
            if income_severity in ("Critical", "High"):
                reasons.append(
                    f"Farmer income faces {income_severity.lower()} stress: lower crop productivity "
                    f"and mandatory shift to lower-gross cereals causes an income deficit of ₹{income_slack_inr:,.0f}."
                )
            if food_severity in ("Critical", "High", "Moderate") and food_slack_pct > 1.0:
                reasons.append(
                    f"Food caloric output experiences a {food_slack_pct:.1f}% gap against target."
                )

            narrative = " ".join(reasons)

        return DiagnosisReport(
            all_targets_met=all_targets_met,
            missed_targets=missed_targets,
            binding_constraints=binding_names,
            primary_bottleneck=primary_bottleneck,
            bottleneck_ranking=bottleneck_ranking,
            narrative_diagnosis=narrative,
        )
