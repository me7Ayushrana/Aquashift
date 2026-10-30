"""Test suite for Phase 3: OR-Tools Optimization Engine.

Covers all 14 required test cases:
1. Valid normal scenario
2. Land conservation
3. Minimum and maximum crop share constraints
4. Nonnegative crop areas
5. Water slack calculation
6. Food slack calculation
7. Income slack calculation
8. Correct income units and accounting
9. Weighted optimization mode
10. Lexicographic priority (Water -> Food -> Income)
11. Invalid hard constraints returning structured diagnostics
12. Deterministic repeated optimization
13. Baseline and optimized metrics consistency
14. Extreme scenario stress test (-80% water, +10% food, +50% income)
"""
import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (
    OptimizationMode,
    OptimizationRequest,
    OptimizationWeights,
)
from backend.app.optimizer import (
    AquaShiftDiagnostician,
    AquaShiftOptimizer,
    AquaShiftStressTester,
    OptimizationValidationException,
)


@pytest.fixture(scope="module")
def optimizer() -> AquaShiftOptimizer:
    return AquaShiftOptimizer()


# -----------------------------------------------------------------------------
# Test 1: Valid Normal Scenario
# -----------------------------------------------------------------------------
def test_1_valid_normal_scenario(optimizer: AquaShiftOptimizer):
    """1. Optimizer executes and produces an optimal, typed solution for normal conditions."""
    req = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="normal",
        optimization_mode=OptimizationMode.WEIGHTED,
    )
    res = optimizer.optimize(req)

    assert res.solver_status == "OPTIMAL"
    assert res.optimization_mode == "weighted"
    assert res.total_land_ha == 10.0
    assert len(res.allocations) == 5
    assert res.solve_time_ms > 0.0
    assert res.objective_value >= 0.0
    assert res.diagnosis.all_targets_met is True
    assert res.water_slack_m3 == 0.0
    assert res.food_slack_kcal == 0.0
    assert res.income_slack_inr == 0.0


# -----------------------------------------------------------------------------
# Test 2: Land Conservation
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("land_ha", [5.0, 10.0, 25.0, 100.0])
def test_2_land_conservation(optimizer: AquaShiftOptimizer, land_ha: float):
    """2. Total allocated hectares across all crops must strictly equal available land."""
    req = OptimizationRequest(
        total_land_ha=land_ha,
        rainfall_scenario="normal",
        optimization_mode=OptimizationMode.WEIGHTED,
    )
    res = optimizer.optimize(req)

    total_allocated = sum(a.allocated_ha for a in res.allocations)
    assert abs(total_allocated - land_ha) < 1e-4, f"Allocated {total_allocated} != land {land_ha}"

    total_pct = sum(a.land_percentage for a in res.allocations)
    assert abs(total_pct - 100.0) < 0.05, f"Percentage sum {total_pct} != 100%"


# -----------------------------------------------------------------------------
# Test 3: Minimum and Maximum Crop Share Constraints
# -----------------------------------------------------------------------------
def test_3_min_max_crop_share_constraints(optimizer: AquaShiftOptimizer):
    """3. Allocated crop areas must strictly respect agronomic min and max land shares."""
    req = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="deficit",
        water_budget_reduction_pct=25.0,
        optimization_mode=OptimizationMode.WEIGHTED,
    )
    res = optimizer.optimize(req)

    for a in res.allocations:
        min_share = float(optimizer.crops_df.loc[a.crop_id, "min_land_share"])
        max_share = float(optimizer.crops_df.loc[a.crop_id, "max_land_share"])
        min_ha = min_share * 10.0
        max_ha = max_share * 10.0

        assert a.allocated_ha >= min_ha - 1e-4, (
            f"Crop {a.crop_id} area {a.allocated_ha} < min {min_ha}"
        )
        assert a.allocated_ha <= max_ha + 1e-4, (
            f"Crop {a.crop_id} area {a.allocated_ha} > max {max_ha}"
        )


# -----------------------------------------------------------------------------
# Test 4: Nonnegative Crop Areas
# -----------------------------------------------------------------------------
def test_4_nonnegative_crop_areas(optimizer: AquaShiftOptimizer):
    """4. Every decision variable allocation must be continuous and nonnegative (x_i >= 0)."""
    for sc in ["normal", "deficit", "severe_deficit", "surplus"]:
        req = OptimizationRequest(
            total_land_ha=10.0,
            rainfall_scenario=sc,
            water_budget_reduction_pct=40.0,
        )
        res = optimizer.optimize(req)
        for a in res.allocations:
            assert a.allocated_ha >= 0.0, f"Negative allocation {a.allocated_ha} for {a.crop_id}"
            assert a.land_percentage >= 0.0


# -----------------------------------------------------------------------------
# Test 5: Water Slack Calculation
# -----------------------------------------------------------------------------
def test_5_water_slack_calculation(optimizer: AquaShiftOptimizer):
    """5. Water slack represents exact nonnegative shortfall beyond available water budget."""
    # Under ample budget: slack must be zero
    req_ample = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=150000.0,
        rainfall_scenario="normal",
    )
    res_ample = optimizer.optimize(req_ample)
    assert res_ample.water_slack_m3 == 0.0
    assert res_ample.total_water_use_m3 <= 150000.0 + 1e-3

    # Under strict deficit where min water exceeds budget
    req_tight = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=10000.0,
        rainfall_scenario="severe_deficit",
        water_availability_ratio=0.20,
    )
    res_tight = optimizer.optimize(req_tight)
    assert res_tight.water_slack_m3 > 0.0
    expected_slack = max(0.0, res_tight.total_water_use_m3 - 10000.0)
    assert abs(res_tight.water_slack_m3 - expected_slack) < 1e-2


# -----------------------------------------------------------------------------
# Test 6: Food Slack Calculation
# -----------------------------------------------------------------------------
def test_6_food_slack_calculation(optimizer: AquaShiftOptimizer):
    """6. Food slack represents exact caloric deficit below nutritional target."""
    req_ample = OptimizationRequest(
        total_land_ha=10.0,
        food_target_kcal=50000000.0,  # 50 million kcal
        rainfall_scenario="normal",
    )
    res_ample = optimizer.optimize(req_ample)
    assert res_ample.food_slack_kcal == 0.0
    assert res_ample.total_food_kcal >= 50000000.0 - 1e-3

    # Impossible target
    req_unreachable = OptimizationRequest(
        total_land_ha=10.0,
        food_target_kcal=500000000.0,  # 500 million kcal
        rainfall_scenario="normal",
    )
    res_unreachable = optimizer.optimize(req_unreachable)
    assert res_unreachable.food_slack_kcal > 0.0
    expected_slack = max(0.0, 500000000.0 - res_unreachable.total_food_kcal)
    assert abs(res_unreachable.food_slack_kcal - expected_slack) < 1e-1


# -----------------------------------------------------------------------------
# Test 7: Income Slack Calculation
# -----------------------------------------------------------------------------
def test_7_income_slack_calculation(optimizer: AquaShiftOptimizer):
    """7. Income slack represents exact net farmer income deficit below target."""
    req_ample = OptimizationRequest(
        total_land_ha=10.0,
        income_target_inr=300000.0,  # ₹3 lakh
        rainfall_scenario="normal",
    )
    res_ample = optimizer.optimize(req_ample)
    assert res_ample.income_slack_inr == 0.0
    assert res_ample.total_net_income_inr >= 300000.0 - 1e-3

    # Unreachable income target
    req_unreachable = OptimizationRequest(
        total_land_ha=10.0,
        income_target_inr=2500000.0,  # ₹25 lakh
        rainfall_scenario="normal",
    )
    res_unreachable = optimizer.optimize(req_unreachable)
    assert res_unreachable.income_slack_inr > 0.0
    expected_slack = max(0.0, 2500000.0 - res_unreachable.total_net_income_inr)
    assert abs(res_unreachable.income_slack_inr - expected_slack) < 1e-1


# -----------------------------------------------------------------------------
# Test 8: Correct Income Units and Accounting
# -----------------------------------------------------------------------------
def test_8_income_units_and_accounting(optimizer: AquaShiftOptimizer):
    """8. Production, quintals, gross revenue, cost, net income, and food formulas match."""
    req = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="normal",
    )
    res = optimizer.optimize(req)

    agg_tonnes = 0.0
    agg_quintals = 0.0
    agg_revenue = 0.0
    agg_cost = 0.0
    agg_food = 0.0
    agg_water = 0.0

    for a in res.allocations:
        price = float(optimizer.crops_df.loc[a.crop_id, "price_inr_quintal"])
        cost_ha = float(optimizer.crops_df.loc[a.crop_id, "cultivation_cost_inr_ha"])
        cal_kg = float(optimizer.crops_df.loc[a.crop_id, "calories_kcal_kg"])

        # Check crop-level identities
        expected_tonnes = round(a.allocated_ha * a.predicted_yield_t_ha, 3)
        assert abs(a.production_tonnes - expected_tonnes) < 1e-2

        expected_quintals = round(a.production_tonnes * 10.0, 2)
        assert abs(a.production_quintals - expected_quintals) < 1e-2

        expected_revenue = round(a.production_quintals * price, 1)
        assert abs(a.gross_revenue_inr - expected_revenue) < 1.0

        expected_cost = round(a.allocated_ha * cost_ha, 1)
        assert abs(a.cultivation_cost_inr - expected_cost) < 1.0

        expected_net_income = round(expected_revenue - expected_cost, 1)
        assert abs(a.net_income_inr - expected_net_income) < 1.0

        expected_food = round(a.production_tonnes * 1000.0 * cal_kg, 1)
        assert abs(a.food_calories_kcal - expected_food) < 10.0

        expected_water = round(a.allocated_ha * a.predicted_water_demand_m3_ha, 1)
        agg_water += expected_water
        agg_tonnes += a.production_tonnes
        agg_quintals += a.production_quintals
        agg_revenue += a.gross_revenue_inr
        agg_cost += a.cultivation_cost_inr
        agg_food += a.food_calories_kcal

    # Check aggregate sums
    assert abs(res.total_gross_revenue_inr - agg_revenue) < 2.0
    assert abs(res.total_cultivation_cost_inr - agg_cost) < 2.0
    assert abs(res.total_net_income_inr - (agg_revenue - agg_cost)) < 2.0
    assert abs(res.total_food_kcal - agg_food) < 20.0
    assert abs(res.total_water_use_m3 - agg_water) < 2.0


# -----------------------------------------------------------------------------
# Test 9: Weighted Optimization Mode
# -----------------------------------------------------------------------------
def test_9_weighted_optimization_mode(optimizer: AquaShiftOptimizer):
    """9. Weighted mode balances priorities according to user-specified weights."""
    # When water budget is tight and income target is high, income-priority solve
    # prioritizes closing income gap, resulting in higher net income and lower income slack
    req_water_prio = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=60000.0,
        food_target_kcal=100000000.0,
        income_target_inr=700000.0,
        rainfall_scenario="normal",
        optimization_mode=OptimizationMode.WEIGHTED,
        weights=OptimizationWeights(water=10.0, food=0.1, income=0.1),
    )
    res_water_prio = optimizer.optimize(req_water_prio)

    req_income_prio = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=60000.0,
        food_target_kcal=100000000.0,
        income_target_inr=700000.0,
        rainfall_scenario="normal",
        optimization_mode=OptimizationMode.WEIGHTED,
        weights=OptimizationWeights(water=0.1, food=0.1, income=10.0),
    )
    res_income_prio = optimizer.optimize(req_income_prio)

    # Income-priority solve achieves higher net income and smaller income slack
    assert res_income_prio.total_net_income_inr > res_water_prio.total_net_income_inr
    assert res_income_prio.income_slack_inr < res_water_prio.income_slack_inr

    # Reject invalid all-zero weights
    with pytest.raises(ValidationError):
        OptimizationWeights(water=0.0, food=0.0, income=0.0)

    # Reject negative weights
    with pytest.raises(ValidationError):
        OptimizationWeights(water=-1.0, food=1.0, income=1.0)


# -----------------------------------------------------------------------------
# Test 10: Lexicographic Priority (Water -> Food -> Income)
# -----------------------------------------------------------------------------
def test_10_lexicographic_priority(optimizer: AquaShiftOptimizer):
    """10. Lexicographic mode optimizes Water -> Food -> Income sequentially."""
    req = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_reduction_pct=35.0,
        rainfall_scenario="deficit",
        optimization_mode=OptimizationMode.LEXICOGRAPHIC,
    )
    res = optimizer.optimize(req)

    assert res.solver_status == "OPTIMAL"
    assert res.optimization_mode == "lexicographic"
    # Water shortfall must be minimized first
    assert res.water_slack_m3 < 1e-3, f"Lexicographic failed to minimize water slack: {res.water_slack_m3}"


# -----------------------------------------------------------------------------
# Test 11: Invalid Hard Constraints Returning Structured Diagnostics
# -----------------------------------------------------------------------------
def test_11_invalid_hard_constraints_diagnostics(optimizer: AquaShiftOptimizer):
    """11. Infeasible hard constraints return structured exceptions, never bare INFEASIBLE or fabricated plans."""
    # Negative land
    with pytest.raises(OptimizationValidationException) as exc1:
        optimizer.validate_hard_constraints(total_land_ha=-5.0, selected_crops=["paddy"])
    assert exc1.value.error_code == "INVALID_LAND_AREA"
    assert "total_land_ha" in exc1.value.conflicting_constraints

    # Empty crop selection
    with pytest.raises(OptimizationValidationException) as exc2:
        optimizer.validate_hard_constraints(total_land_ha=10.0, selected_crops=[])
    assert exc2.value.error_code == "EMPTY_CROP_SELECTION"

    # Unknown crop
    with pytest.raises(OptimizationValidationException) as exc3:
        optimizer.validate_hard_constraints(total_land_ha=10.0, selected_crops=["coffee"])
    assert exc3.value.error_code == "UNKNOWN_CROP"

    # Underutilizing land (only Millets max share 0.50 selected, cannot reach 1.0)
    with pytest.raises(OptimizationValidationException) as exc4:
        optimizer.optimize(OptimizationRequest(total_land_ha=10.0, selected_crops=["millets"]))
    assert exc4.value.error_code == "MAX_SHARES_UNDERUTILIZE_LAND"
    assert "max_land_shares_sum" in exc4.value.conflicting_constraints


# -----------------------------------------------------------------------------
# Test 12: Deterministic Repeated Optimization
# -----------------------------------------------------------------------------
def test_12_deterministic_repeated_optimization(optimizer: AquaShiftOptimizer):
    """12. Identical optimization requests must produce bit-for-bit identical results across 5 runs."""
    req = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_reduction_pct=20.0,
        rainfall_scenario="deficit",
        optimization_mode=OptimizationMode.WEIGHTED,
    )

    baseline_res = optimizer.optimize(req)
    for run in range(4):
        res = optimizer.optimize(req)
        assert res.objective_value == baseline_res.objective_value
        assert res.total_water_use_m3 == baseline_res.total_water_use_m3
        assert res.total_food_kcal == baseline_res.total_food_kcal
        assert res.total_net_income_inr == baseline_res.total_net_income_inr
        for a1, a2 in zip(baseline_res.allocations, res.allocations):
            assert a1.allocated_ha == a2.allocated_ha
            assert a1.net_income_inr == a2.net_income_inr


# -----------------------------------------------------------------------------
# Test 13: Baseline and Optimized Metrics Consistency
# -----------------------------------------------------------------------------
def test_13_baseline_and_optimized_consistency(optimizer: AquaShiftOptimizer):
    """13. Baseline comparison cards use consistent accounting formulas and delta arithmetic."""
    req = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="normal",
    )
    res = optimizer.optimize(req)

    assert "water" in res.baseline_comparison
    assert "food" in res.baseline_comparison
    assert "income" in res.baseline_comparison

    # Baseline Punjab 10 ha (7 ha Paddy, 3 ha Maize) under normal conditions:
    # Water ~104,127 m³, Food ~162.75M kcal, Net income ~₹641,110
    w_comp = res.baseline_comparison["water"]
    assert abs(w_comp.baseline_value - 104127.3) < 100.0
    assert abs(w_comp.optimized_value - res.total_water_use_m3) < 0.1
    assert abs(w_comp.delta_value - (w_comp.optimized_value - w_comp.baseline_value)) < 0.1

    f_comp = res.baseline_comparison["food"]
    assert abs(f_comp.baseline_value - 162750000.0) < 10000.0
    assert abs(f_comp.optimized_value - res.total_food_kcal) < 0.1
    assert abs(f_comp.delta_value - (f_comp.optimized_value - f_comp.baseline_value)) < 0.1

    i_comp = res.baseline_comparison["income"]
    assert abs(i_comp.baseline_value - 641110.0) < 1000.0
    assert abs(i_comp.optimized_value - res.total_net_income_inr) < 0.1
    assert abs(i_comp.delta_value - (i_comp.optimized_value - i_comp.baseline_value)) < 0.1


# -----------------------------------------------------------------------------
# Test 14: Extreme Scenario Stress Test
# -----------------------------------------------------------------------------
def test_14_extreme_scenario_stress_test(optimizer: AquaShiftOptimizer):
    """14. Extreme scenario (-80% water, +10% food, +50% income):
    - Strict solve is INFEASIBLE.
    - Soft recovery solve is OPTIMAL with closest-feasible plan (Pulses 5 ha, Millets 5 ha).
    - Bottleneck diagnosis ranking: Water: Critical, Income: High, Food: Moderate.
    """
    tester = AquaShiftStressTester(optimizer=optimizer)
    res = tester.run_stress_test()

    # 1. Strict solve fails
    assert res.strict_solve_status == "INFEASIBLE"
    assert "INFEASIBLE" in res.strict_solve_message
    assert "independently infeasible" in res.strict_solve_message.lower()

    # 2. Recovery solve succeeds
    assert res.recovery_solve_status == "OPTIMAL"
    plan = res.closest_feasible_plan

    # Land conservation in recovery
    assert abs(plan.total_land_ha - 10.0) < 1e-4

    # Allocations pivot entirely to drought-tolerant Pulses and Millets
    alloc_dict = {a.crop_id: a.allocated_ha for a in plan.allocations}
    assert alloc_dict["paddy"] == 0.0
    assert alloc_dict["wheat"] == 0.0
    assert alloc_dict["maize"] == 0.0
    assert alloc_dict["pulses"] == 5.0
    assert alloc_dict["millets"] == 5.0

    # 3. Bottleneck ranking
    diag = plan.diagnosis
    assert diag.all_targets_met is False
    assert set(diag.missed_targets) == {"Water", "Food", "Income"}
    assert diag.primary_bottleneck == "Water"

    ranks = {b.rank: (b.dimension, b.severity) for b in diag.bottleneck_ranking}
    assert ranks[1] == ("Water", "Critical")
    assert ranks[2] == ("Income", "High")
    assert ranks[3] == ("Food", "High")

    # Verify sensitivity label
    for sens in plan.local_sensitivities:
        assert "local model sensitivity" in sens.interpretation.lower()


# -----------------------------------------------------------------------------
# Test 15: Individual and Joint Feasibility Audit
# -----------------------------------------------------------------------------
def test_15_individual_and_joint_feasibility_audit(optimizer: AquaShiftOptimizer):
    """15. Rigorously audits independent vs joint feasibility under extreme stress:
    - Verifies water budget is independently proven infeasible.
    - Verifies food target is independently proven infeasible.
    - Verifies income target is independently proven infeasible.
    - Verifies all joint pairs and triplet are infeasible.
    """
    tester = AquaShiftStressTester(optimizer=optimizer)
    res = tester.run_stress_test()

    ind = res.individual_feasibility
    assert ind["water"] is False, "Water budget should be independently infeasible under -80% drought"
    assert ind["food"] is False, "Food target (+10%) should be independently infeasible under severe drought"
    assert ind["income"] is False, "Income target (+50%) should be independently infeasible under severe drought"

    joint = res.joint_feasibility
    assert joint["water_and_food"] is False
    assert joint["water_and_income"] is False
    assert joint["food_and_income"] is False
    assert joint["all_three"] is False

    bounds = res.target_boundaries
    assert bounds["water"]["min_achievable"] > bounds["water"]["budget"]
    assert bounds["food"]["max_achievable"] < bounds["food"]["target"]
    assert bounds["income"]["max_achievable"] < bounds["income"]["target"]


# -----------------------------------------------------------------------------
# Test 16: Diagnosis Ranking Logic and Edge Cases
# -----------------------------------------------------------------------------
def test_16_diagnosis_ranking_logic_and_edge_cases(optimizer: AquaShiftOptimizer):
    """16. Tests diagnosis ranking formula across multiple boundary edge cases:
    - All targets satisfied -> all dimensions Satisfied, no primary bottleneck.
    - Water-only bottleneck -> Water is Rank 1, others Satisfied.
    - Income-only bottleneck -> Income is Rank 1, others Satisfied.
    - Food-only bottleneck -> Food is Rank 1, others Satisfied.
    """
    # Edge case 1: All satisfied
    req_all_met = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="normal",
    )
    res_all_met = optimizer.optimize(req_all_met)
    diag_all = res_all_met.diagnosis
    assert diag_all.all_targets_met is True
    assert diag_all.primary_bottleneck is None
    for b in diag_all.bottleneck_ranking:
        assert b.severity == "Satisfied"
        assert b.slack_amount == 0.0

    # Edge case 2: Water only missed
    req_water_missed = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=20000.0,
        food_target_kcal=30000000.0,  # easily achievable
        income_target_inr=200000.0,  # easily achievable
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
    )
    res_water_missed = optimizer.optimize(req_water_missed)
    diag_water = res_water_missed.diagnosis
    assert diag_water.missed_targets == ["Water"]
    assert diag_water.bottleneck_ranking[0].dimension == "Water"
    assert diag_water.primary_bottleneck == "Water"

    # Edge case 3: Income only missed
    req_income_missed = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=120000.0,  # abundant water
        food_target_kcal=30000000.0,  # easily achievable
        income_target_inr=1500000.0,  # unachievable high income target
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
    )
    res_income_missed = optimizer.optimize(req_income_missed)
    diag_income = res_income_missed.diagnosis
    assert diag_income.missed_targets == ["Income"]
    assert diag_income.bottleneck_ranking[0].dimension == "Income"
    assert diag_income.primary_bottleneck == "Income"

    # Edge case 4: Food only missed
    req_food_missed = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_m3=120000.0,
        food_target_kcal=350000000.0,  # unachievable high food target
        income_target_inr=200000.0,
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
    )
    res_food_missed = optimizer.optimize(req_food_missed)
    diag_food = res_food_missed.diagnosis
    assert diag_food.missed_targets == ["Food"]
    assert diag_food.bottleneck_ranking[0].dimension == "Food"
    assert diag_food.primary_bottleneck == "Food"


# -----------------------------------------------------------------------------
# Test 17: Lexicographic Tolerance and Multi-Stage Preservation
# -----------------------------------------------------------------------------
def test_17_lexicographic_tolerance_and_multistage_preservation(optimizer: AquaShiftOptimizer):
    """17. Verifies multi-stage lexicographic solve strictly preserves prior objectives:
    - Phase 1 water objective is preserved within numerical tolerance in Phase 2 & 3.
    - Final allocations and slacks correspond to Phase 3 solve.
    """
    req = OptimizationRequest(
        total_land_ha=10.0,
        water_budget_reduction_pct=35.0,
        rainfall_scenario="deficit",
        optimization_mode=OptimizationMode.LEXICOGRAPHIC,
    )
    res = optimizer.optimize(req)

    # In deficit with 35% cut, water is tightly constrained.
    # Lexicographic solve prioritizes water first:
    assert res.water_slack_m3 < 1e-3, f"Water slack {res.water_slack_m3} not preserved at 0.0"

    # Verify decision variables sum exactly to total land
    tot_area = sum(a.allocated_ha for a in res.allocations)
    assert abs(tot_area - 10.0) < 1e-4

    # Verify that returned allocations match the reported metrics
    computed_water = sum(a.allocated_ha * a.predicted_water_demand_m3_ha for a in res.allocations)
    assert abs(res.total_water_use_m3 - computed_water) < 1.0


# -----------------------------------------------------------------------------
# Test 18: Food Severity Classification Rules & Independence from Farm Income
# -----------------------------------------------------------------------------
def test_18_food_severity_classification_rules():
    """18. Tests food severity classification:
    - Satisfied: slack <= 1000 kcal tolerance
    - Moderate: 0 < shortfall < 50%
    - High: shortfall >= 50%
    - Independence: food severity must not be downgraded merely because income is negative.
    Tests all 5 required conditions:
    1. Food shortfall of 10% -> Moderate
    2. Food shortfall of 50% -> High
    3. Food shortfall of 95% -> High
    4. Food shortfall of 95% while income is negative -> High
    5. All targets satisfied -> Satisfied
    """
    # 1. Food shortfall of 10% (moderate)
    diag_10 = AquaShiftDiagnostician.diagnose(
        allocations=[],
        water_achieved_m3=50000.0,
        water_budget_m3=50000.0,
        water_slack_m3=0.0,
        food_achieved_kcal=90000000.0,
        food_target_kcal=100000000.0,
        food_slack_kcal=10000000.0,  # 10% shortfall
        income_achieved_inr=500000.0,
        income_target_inr=500000.0,
        income_slack_inr=0.0,
        min_feasible_water_m3=30000.0,
        binding_constraints=[],
    )
    food_rank_10 = next(b for b in diag_10.bottleneck_ranking if b.dimension == "Food")
    assert food_rank_10.severity == "Moderate"
    assert food_rank_10.slack_percentage == 10.0

    # 2. Food shortfall of 50% (high threshold boundary)
    diag_50 = AquaShiftDiagnostician.diagnose(
        allocations=[],
        water_achieved_m3=50000.0,
        water_budget_m3=50000.0,
        water_slack_m3=0.0,
        food_achieved_kcal=50000000.0,
        food_target_kcal=100000000.0,
        food_slack_kcal=50000000.0,  # 50% shortfall
        income_achieved_inr=500000.0,
        income_target_inr=500000.0,
        income_slack_inr=0.0,
        min_feasible_water_m3=30000.0,
        binding_constraints=[],
    )
    food_rank_50 = next(b for b in diag_50.bottleneck_ranking if b.dimension == "Food")
    assert food_rank_50.severity == "High"
    assert food_rank_50.slack_percentage == 50.0

    # 3. Food shortfall of 95% (high)
    diag_95 = AquaShiftDiagnostician.diagnose(
        allocations=[],
        water_achieved_m3=50000.0,
        water_budget_m3=50000.0,
        water_slack_m3=0.0,
        food_achieved_kcal=5000000.0,
        food_target_kcal=100000000.0,
        food_slack_kcal=95000000.0,  # 95% shortfall
        income_achieved_inr=500000.0,
        income_target_inr=500000.0,
        income_slack_inr=0.0,
        min_feasible_water_m3=30000.0,
        binding_constraints=[],
    )
    food_rank_95 = next(b for b in diag_95.bottleneck_ranking if b.dimension == "Food")
    assert food_rank_95.severity == "High"
    assert food_rank_95.slack_percentage == 95.0

    # 4. Food shortfall of 95% while income is negative (must NOT be downgraded to Moderate)
    diag_95_neg_inc = AquaShiftDiagnostician.diagnose(
        allocations=[],
        water_achieved_m3=20000.0,
        water_budget_m3=10000.0,
        water_slack_m3=10000.0,
        food_achieved_kcal=5000000.0,
        food_target_kcal=100000000.0,
        food_slack_kcal=95000000.0,  # 95% shortfall
        income_achieved_inr=-150000.0,  # negative income!
        income_target_inr=500000.0,
        income_slack_inr=650000.0,
        min_feasible_water_m3=25000.0,
        binding_constraints=[],
    )
    food_rank_neg = next(b for b in diag_95_neg_inc.bottleneck_ranking if b.dimension == "Food")
    assert food_rank_neg.severity == "High", "Food shortfall of 95% must remain High even when income is negative"
    assert food_rank_neg.slack_percentage == 95.0

    # 5. All targets satisfied (slack <= tolerance)
    diag_sat = AquaShiftDiagnostician.diagnose(
        allocations=[],
        water_achieved_m3=40000.0,
        water_budget_m3=50000.0,
        water_slack_m3=0.0,
        food_achieved_kcal=105000000.0,
        food_target_kcal=100000000.0,
        food_slack_kcal=0.0,
        income_achieved_inr=550000.0,
        income_target_inr=500000.0,
        income_slack_inr=0.0,
        min_feasible_water_m3=30000.0,
        binding_constraints=[],
    )
    assert diag_sat.all_targets_met is True
    assert diag_sat.primary_bottleneck is None
    for b in diag_sat.bottleneck_ranking:
        assert b.severity == "Satisfied"
        assert b.slack_amount == 0.0


# -----------------------------------------------------------------------------
# Test 19: End-to-End Food Units, Feasibility Boundaries and Consistency
# -----------------------------------------------------------------------------
def test_19_food_units_and_feasibility_boundaries(optimizer: AquaShiftOptimizer):
    """19. Audits food units end-to-end:
    - Verifies formula: Food (kcal) = area (ha) * yield (t/ha) * 1000 (kg/t) * cal (kcal/kg).
    - Verifies normal baseline food of 162.75M kcal and +10% target of 179.025M kcal.
    - Verifies maximum achievable food under severe drought is 19.30M kcal (19,299,400 kcal)
      derived from 8 ha wheat + 2 ha millets.
    - Verifies mathematical consistency between optimizer and stress-test boundaries.
    """
    # 1. Food production unit audit across allocations
    req = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
    )
    res = optimizer.optimize(req)

    # Check each individual crop allocation
    computed_total_food = 0.0
    for a in res.allocations:
        cal_kg = float(optimizer.crops_df.loc[a.crop_id, "calories_kcal_kg"])
        # Production in tonnes: area (ha) * yield (t/ha) rounded to kg precision (3 decimal places)
        expected_tonnes = round(a.allocated_ha * a.predicted_yield_t_ha, 3)
        assert abs(a.production_tonnes - expected_tonnes) < 1e-4

        # Food calories (kcal): production_tonnes * 1000 (kg/tonne) * calories (kcal/kg)
        expected_food_from_prod = round(a.production_tonnes * 1000.0 * cal_kg, 1)
        assert abs(a.food_calories_kcal - expected_food_from_prod) < 1.0

        # Direct unrounded formula matches within 0.0005 t (0.5 kg) * cal_kg
        direct_formula = a.allocated_ha * a.predicted_yield_t_ha * 1000.0 * cal_kg
        assert abs(a.food_calories_kcal - direct_formula) <= (cal_kg * 0.5 + 1.0)

        computed_total_food += a.food_calories_kcal

    assert abs(res.total_food_kcal - computed_total_food) < 1.0

    # 2. Baseline food and target calculation
    _, baseline = optimizer.calculate_baseline(
        total_land_ha=10.0,
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
        selected_crops=["paddy", "wheat", "maize", "pulses", "millets"],
    )
    # Baseline: 7 ha paddy (7 * 4.755 * 1000 * 3600 = 119.826M) + 3 ha maize (3 * 3.920 * 1000 * 3650 = 42.924M) = 162.75M kcal
    assert baseline["total_food_kcal"] == 162750000.0, f"Expected 162.75M kcal baseline, got {baseline['total_food_kcal']}"

    # Target calculation with +10% increase
    req_target_pct = OptimizationRequest(
        total_land_ha=10.0,
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
        food_target_increase_pct=10.0,
    )
    res_target = optimizer.optimize(req_target_pct)
    expected_target = round(162750000.0 * 1.10, 1)  # 179,025,000.0 kcal
    assert res_target.food_target_kcal == expected_target

    # 3. Maximum achievable food boundary under severe drought
    # ML predictions under severe deficit (ratio=0.20):
    # wheat: 0.587 t/ha * 1000 * 3400 = 1,995,800 kcal/ha (max share 80% = 8.0 ha) -> 15,966,400 kcal
    # millets: 0.505 t/ha * 1000 * 3300 = 1,666,500 kcal/ha (remaining 20% = 2.0 ha) -> 3,333,000 kcal
    # All other crops: yield = 0.05 t/ha -> caloric density < 185,000 kcal/ha
    # Total analytical max food = 15,966,400 + 3,333,000 = 19,299,400 kcal (19.30M kcal)
    severe_preds = optimizer.predictor.predict_all_crops(
        rainfall_scenario="severe_deficit",
        water_availability_ratio=0.20,
        crops=["paddy", "wheat", "maize", "pulses", "millets"],
    ).predictions

    severe_food_coeffs = {
        c: severe_preds[c].predicted_yield_t_ha * 1000.0 * float(optimizer.crops_df.loc[c, "calories_kcal_kg"])
        for c in ["paddy", "wheat", "maize", "pulses", "millets"]
    }
    max_food_drought = optimizer.calculate_maximum_feasible_food(
        total_land_ha=10.0,
        selected_crops=["paddy", "wheat", "maize", "pulses", "millets"],
        predicted_food_coeffs=severe_food_coeffs,
    )
    assert abs(max_food_drought - 19299400.0) < 1.0, f"Expected 19.30M kcal (19,299,400), got {max_food_drought}"

    # 4. Consistency between optimizer and stress-test calculations
    tester = AquaShiftStressTester(optimizer=optimizer)
    stress_res = tester.run_stress_test()

    assert abs(stress_res.target_boundaries["food"]["max_achievable"] - max_food_drought) < 1.0
    assert stress_res.target_boundaries["food"]["target"] == expected_target

    # Verify slack consistency: slack = max(0.0, target - achieved)
    plan = stress_res.closest_feasible_plan
    expected_slack = round(max(0.0, plan.food_target_kcal - plan.total_food_kcal), 1)
    assert abs(plan.food_slack_kcal - expected_slack) < 1.0
    expected_shortfall_pct = round((expected_slack / plan.food_target_kcal) * 100.0, 1)
    assert abs(plan.food_shortfall_pct - expected_shortfall_pct) < 0.2

