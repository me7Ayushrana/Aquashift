"""API integration tests for Phase 4: FastAPI Endpoints & Pipeline Integration.

Tests all required endpoints and edge cases using FastAPI TestClient:
1. Invalid land area (<= 0).
2. Invalid rainfall scenario.
3. Invalid optimization mode.
4. Negative water budget.
5. Malformed request payload.
6. Optimizer hard-constraint failure (structured diagnostics, no 500).
7. Extreme drought stress-test response.
8. Consistency between /api/predict and /api/optimize predictions.
9. Consistency between /api/baseline and internal baseline calculations.
10. Sweep output contains ordered water availability points and valid numeric results.
11. Caching of identical scenario requests.
12. OpenAPI and Swagger documentation availability.
"""
import threading
import pytest
from starlette.testclient import TestClient

from backend.app.core.cache import ScenarioCache, scenario_cache
from backend.app.main import app
from backend.app.ml.predictor import AquaShiftPredictor
from backend.app.models.schemas import (
    BatchPredictionRequest,
    OptimizationRequest,
    OptimizationWeights,
    SweepRequest,
)
from backend.app.optimizer import AquaShiftOptimizer
from backend.app.optimizer.stress import AquaShiftStressTester
from backend.app.optimizer.sweep import AquaShiftWaterSweep

client = TestClient(app)


# -----------------------------------------------------------------------------
# Standard Endpoint Happy Path Tests
# -----------------------------------------------------------------------------

def test_api_health_endpoint():
    """Verify GET /api/health returns 200 with operational status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["service"] == "AquaShift Backend"
    assert data["offline_mode"] is True


def test_api_config_endpoint():
    """Verify GET /api/config returns metadata, crops, scenarios, input ranges, and units."""
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert len(data["crops"]) == 5
    crop_ids = [c["crop_id"] for c in data["crops"]]
    assert set(crop_ids) == {"paddy", "wheat", "maize", "pulses", "millets"}
    assert len(data["rainfall_scenarios"]) == 4
    scenario_ids = [s["scenario_id"] for s in data["rainfall_scenarios"]]
    assert set(scenario_ids) == {"normal", "deficit", "severe_deficit", "surplus"}
    assert "weighted" in data["optimization_modes"]
    assert "lexicographic" in data["optimization_modes"]
    assert len(data["input_ranges"]) >= 5
    assert "units" in data
    assert "baseline_assumptions" in data


def test_api_baseline_endpoint():
    """Verify GET /api/baseline returns reference Punjab/Haryana 10 ha baseline."""
    res = client.get("/api/baseline?total_land_ha=10.0")
    assert res.status_code == 200
    data = res.json()
    assert data["total_land_ha"] == 10.0
    assert data["total_food_kcal"] == 162750000.0  # 162.75M kcal
    assert data["total_water_use_m3"] > 80000.0
    assert data["total_net_income_inr"] > 500000.0
    assert len(data["allocations"]) == 5
    alloc_map = {a["crop_id"]: a["allocated_ha"] for a in data["allocations"]}
    assert alloc_map["paddy"] == 7.0
    assert alloc_map["maize"] == 3.0
    assert alloc_map["wheat"] == 0.0


def test_api_predict_endpoint():
    """Verify POST /api/predict returns predictions for all 5 crops with uncertainty margins."""
    payload = {
        "rainfall_scenario": "deficit",
        "water_availability_ratio": 0.80,
    }
    res = client.post("/api/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["rainfall_scenario"] == "deficit"
    assert data["water_availability_ratio"] == 0.80
    assert len(data["predictions"]) == 5
    for c in ["paddy", "wheat", "maize", "pulses", "millets"]:
        pred = data["predictions"][c]
        assert pred["predicted_yield_t_ha"] >= 0.05
        assert pred["predicted_water_demand_m3_ha"] >= 200.0
        assert pred["yield_range_lower"] <= pred["predicted_yield_t_ha"] <= pred["yield_range_upper"]
        assert pred["water_range_lower"] <= pred["predicted_water_demand_m3_ha"] <= pred["water_range_upper"]
    assert "units" in data
    assert "uncertainty_note" in data


def test_api_optimize_endpoint_weighted():
    """Verify POST /api/optimize runs weighted mode successfully."""
    payload = {
        "total_land_ha": 10.0,
        "rainfall_scenario": "normal",
        "water_availability_ratio": 1.0,
        "optimization_mode": "weighted",
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert abs(data["total_land_ha"] - 10.0) < 1e-3
    assert len(data["allocations"]) == 5
    assert data["total_water_use_m3"] > 0.0
    assert data["total_food_kcal"] > 0.0
    assert "diagnosis" in data
    assert data["diagnosis"]["all_targets_met"] is True


def test_api_optimize_endpoint_lexicographic():
    """Verify POST /api/optimize runs lexicographic mode successfully."""
    payload = {
        "total_land_ha": 10.0,
        "water_budget_reduction_pct": 20.0,
        "rainfall_scenario": "deficit",
        "optimization_mode": "lexicographic",
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["optimization_mode"] == "lexicographic"
    assert data["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert abs(data["total_land_ha"] - 10.0) < 1e-3


# -----------------------------------------------------------------------------
# Required Error & Validation Tests (1 to 6)
# -----------------------------------------------------------------------------

def test_1_invalid_land_area():
    """1. Total land area <= 0 must be rejected with HTTP 422."""
    res_zero = client.post("/api/optimize", json={"total_land_ha": 0.0})
    assert res_zero.status_code == 422
    data_zero = res_zero.json()
    assert "detail" in data_zero or "message" in data_zero

    res_neg = client.post("/api/optimize", json={"total_land_ha": -10.0})
    assert res_neg.status_code == 422


def test_2_invalid_rainfall_scenario():
    """2. Unknown rainfall scenario must be rejected with HTTP 422."""
    # Test on /api/optimize
    res_opt = client.post("/api/optimize", json={"rainfall_scenario": "cyclone_tsunami"})
    assert res_opt.status_code == 422
    assert "cyclone_tsunami" in str(res_opt.json())

    # Test on /api/predict
    res_pred = client.post("/api/predict", json={"rainfall_scenario": "hurricane"})
    assert res_pred.status_code == 422
    assert "hurricane" in str(res_pred.json())


def test_3_invalid_optimization_mode():
    """3. Unknown optimization mode must be rejected with HTTP 422."""
    res = client.post("/api/optimize", json={"optimization_mode": "quantum_annealing"})
    assert res.status_code == 422


def test_4_negative_water_budget():
    """4. Negative water budget must be rejected with HTTP 422."""
    res = client.post("/api/optimize", json={"water_budget_m3": -500.0})
    assert res.status_code == 422


def test_5_malformed_request_payload():
    """5. Malformed non-JSON payload must be rejected with HTTP 422."""
    res = client.post(
        "/api/optimize",
        content="this is not valid json at all!",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422


def test_6_optimizer_hard_constraint_failure():
    """6. Contradictory hard constraints must return structured 422 without Python traceback."""
    # Pulses max_land_share is 50%. Selecting pulses alone makes total allowable max share 50% < 100%.
    payload = {
        "total_land_ha": 10.0,
        "selected_crops": ["pulses"],
        "rainfall_scenario": "normal",
    }
    res = client.post("/api/optimize", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert data["error"] == "Optimization Validation Error"
    assert data["error_code"] == "MAX_SHARES_UNDERUTILIZE_LAND"
    assert "strictly less than 1.00" in data["message"]
    assert "max_land_shares_sum" in data["conflicting_constraints"]
    # Ensure no internal Python traceback leaked to client
    assert "Traceback" not in res.text


# -----------------------------------------------------------------------------
# Extreme Stress, Consistency & Sweep Tests (7 to 10)
# -----------------------------------------------------------------------------

def test_7_extreme_drought_stress_test_response():
    """7. Extreme drought stress test returns structured diagnosis with Water Critical, Income High, Food High."""
    res = client.post("/api/stress-test", json={})
    assert res.status_code == 200
    data = res.json()

    # Strict solve fails
    assert data["strict_solve_status"] == "INFEASIBLE"
    assert "compound infeasibility" in data["strict_solve_message"].lower()

    # Recovery solve succeeds
    assert data["recovery_solve_status"] == "OPTIMAL"
    plan = data["closest_feasible_plan"]
    assert abs(plan["total_land_ha"] - 10.0) < 1e-3

    # Feasibility breakdown
    assert data["individual_feasibility"]["water"] is False
    assert data["individual_feasibility"]["food"] is False
    assert data["individual_feasibility"]["income"] is False

    # Bottleneck diagnosis ranking
    ranking = plan["diagnosis"]["bottleneck_ranking"]
    assert ranking[0]["dimension"] == "Water"
    assert ranking[0]["severity"] == "Critical"
    assert ranking[1]["dimension"] == "Income"
    assert ranking[1]["severity"] == "High"
    assert ranking[2]["dimension"] == "Food"
    assert ranking[2]["severity"] == "High"


def test_8_consistency_predict_and_optimize():
    """8. ML predictions returned by /api/predict match the predictions used inside /api/optimize."""
    scenario = "deficit"
    water_ratio = 0.70

    # Call /api/predict
    res_pred = client.post(
        "/api/predict",
        json={"rainfall_scenario": scenario, "water_availability_ratio": water_ratio},
    )
    assert res_pred.status_code == 200
    preds = res_pred.json()["predictions"]

    # Call /api/optimize
    res_opt = client.post(
        "/api/optimize",
        json={
            "total_land_ha": 10.0,
            "rainfall_scenario": scenario,
            "water_availability_ratio": water_ratio,
        },
    )
    assert res_opt.status_code == 200
    opt_allocs = res_opt.json()["allocations"]

    for a in opt_allocs:
        cid = a["crop_id"]
        assert cid in preds
        assert abs(a["predicted_yield_t_ha"] - preds[cid]["predicted_yield_t_ha"]) < 1e-3
        assert abs(a["predicted_water_demand_m3_ha"] - preds[cid]["predicted_water_demand_m3_ha"]) < 1e-1


def test_9_consistency_baseline_and_calculations():
    """9. Baseline API endpoint matches direct optimizer.calculate_baseline outputs."""
    res = client.get("/api/baseline?total_land_ha=10.0&rainfall_scenario=normal&water_availability_ratio=1.0")
    assert res.status_code == 200
    api_data = res.json()

    optimizer = AquaShiftOptimizer()
    _, baseline_metrics = optimizer.calculate_baseline(
        total_land_ha=10.0,
        rainfall_scenario="normal",
        water_availability_ratio=1.0,
        selected_crops=optimizer.all_crops,
    )

    assert abs(api_data["total_water_use_m3"] - baseline_metrics["total_water_use_m3"]) < 1e-1
    assert abs(api_data["total_food_kcal"] - baseline_metrics["total_food_kcal"]) < 1e-1
    assert abs(api_data["total_gross_revenue_inr"] - baseline_metrics["total_gross_revenue_inr"]) < 1e-1
    assert abs(api_data["total_cultivation_cost_inr"] - baseline_metrics["total_cultivation_cost_inr"]) < 1e-1
    assert abs(api_data["total_net_income_inr"] - baseline_metrics["total_net_income_inr"]) < 1e-1


def test_10_sweep_output_ordered_and_valid():
    """10. Sweep endpoint returns strictly ordered water availability points with valid numeric metrics."""
    payload = {
        "total_land_ha": 10.0,
        "rainfall_scenario": "normal",
        "start_ratio": 1.0,
        "end_ratio": 0.20,
        "step": 0.10,
    }
    res = client.post("/api/simulate/sweep", json=payload)
    assert res.status_code == 200
    data = res.json()
    points = data["points"]

    assert len(points) == 9
    ratios = [p["water_availability_ratio"] for p in points]
    # Check strictly monotonically decreasing
    for i in range(len(ratios) - 1):
        assert ratios[i] > ratios[i + 1]

    # Check first and last point bounds
    assert ratios[0] == 1.0
    assert ratios[-1] == 0.20

    # Verify points contain valid numeric allocations and totals
    for p in points:
        assert p["water_budget_m3"] > 0.0
        assert p["total_water_use_m3"] > 0.0
        assert p["total_food_kcal"] > 0.0
        total_ha = sum(p["allocations_ha"].values())
        assert abs(total_ha - 10.0) < 1e-3
        total_pct = sum(p["allocations_pct"].values())
        assert abs(total_pct - 100.0) < 1e-2

    # Tipping point detection
    assert data["tipping_point_water_ratio"] is not None
    assert data["tipping_point_description"] is not None


# -----------------------------------------------------------------------------
# Additional Architectural Verification: Caching & Docs
# -----------------------------------------------------------------------------

def test_11_cache_hit_on_identical_request():
    """11. Identical optimization requests return identical cached outputs."""
    payload = {
        "total_land_ha": 15.0,
        "water_budget_reduction_pct": 25.0,
        "rainfall_scenario": "deficit",
    }
    res1 = client.post("/api/optimize", json=payload)
    res2 = client.post("/api/optimize", json=payload)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json() == res2.json()


def test_12_docs_and_openapi_endpoints():
    """12. /docs and /openapi.json are accessible and contain all Phase 4 endpoints."""
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    assert "swagger" in res_docs.text.lower() or "html" in res_docs.text.lower()

    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code == 200
    schema = res_openapi.json()
    paths = schema["paths"]
    assert "/api/health" in paths
    assert "/api/config" in paths
    assert "/api/baseline" in paths
    assert "/api/predict" in paths
    assert "/api/optimize" in paths
    assert "/api/stress-test" in paths
    assert "/api/simulate/sweep" in paths


# -----------------------------------------------------------------------------
# Phase 4 Targeted Audit: Numerical Consistency, Regression, Caching & Sweeps
# -----------------------------------------------------------------------------

def test_13_canonical_baseline_regression_and_kpis():
    """13. Regression: Verify /api/baseline exactly matches the canonical 7 ha Paddy + 3 ha Maize baseline."""
    res = client.get("/api/baseline?total_land_ha=10.0")
    assert res.status_code == 200
    data = res.json()

    # 1. Exact crop allocation verification
    alloc_map = {a["crop_id"]: a for a in data["allocations"]}
    assert len(alloc_map) == 5
    assert alloc_map["paddy"]["allocated_ha"] == 7.0
    assert alloc_map["paddy"]["land_percentage"] == 70.0
    assert alloc_map["maize"]["allocated_ha"] == 3.0
    assert alloc_map["maize"]["land_percentage"] == 30.0
    assert alloc_map["wheat"]["allocated_ha"] == 0.0
    assert alloc_map["pulses"]["allocated_ha"] == 0.0
    assert alloc_map["millets"]["allocated_ha"] == 0.0

    # 2. Exact KPI values
    assert abs(data["total_food_kcal"] - 162750000.0) < 1e-1
    assert abs(data["total_water_use_m3"] - 104127.3) < 1e-1
    assert abs(data["total_gross_revenue_inr"] - 985110.0) < 1e-1
    assert abs(data["total_cultivation_cost_inr"] - 344000.0) < 1e-1
    assert abs(data["total_net_income_inr"] - 641110.0) < 1e-1

    # 3. Direct comparison with optimizer engine
    opt = AquaShiftOptimizer()
    areas, metrics = opt.calculate_baseline(10.0, "normal", 1.0, opt.all_crops)
    assert areas["paddy"] == 7.0
    assert areas["maize"] == 3.0
    assert abs(data["total_food_kcal"] - metrics["total_food_kcal"]) < 1e-3
    assert abs(data["total_water_use_m3"] - metrics["total_water_use_m3"]) < 1e-3
    assert abs(data["total_net_income_inr"] - metrics["total_net_income_inr"]) < 1e-3

    # 4. Alignment with /api/config baseline assumptions
    cfg_res = client.get("/api/config")
    assert cfg_res.status_code == 200
    cfg_base = cfg_res.json()["baseline_assumptions"]
    assert cfg_base["paddy_share"] == 0.70
    assert cfg_base["maize_share"] == 0.30
    assert abs(cfg_base["baseline_water_m3"] - 104127.3) < 1e-1
    assert abs(cfg_base["baseline_food_kcal"] - 162750000.0) < 1e-1
    assert abs(cfg_base["baseline_net_income_inr"] - 641110.0) < 1e-1


def test_14_numerical_parity_predict_endpoint():
    """14. Numerical parity: /api/predict matches AquaShiftPredictor for identical inputs within 1e-4."""
    predictor = AquaShiftPredictor()
    scenarios = ["normal", "deficit", "severe_deficit", "surplus"]
    ratios = [0.4, 0.8, 1.0]

    for sc in scenarios:
        for r in ratios:
            payload = {"rainfall_scenario": sc, "water_availability_ratio": r}
            res = client.post("/api/predict", json=payload)
            assert res.status_code == 200
            api_preds = res.json()["predictions"]

            core_preds = predictor.predict_all_crops(
                rainfall_scenario=sc,
                water_availability_ratio=r,
            ).predictions

            for cid, cp in core_preds.items():
                ap = api_preds[cid]
                assert abs(ap["predicted_yield_t_ha"] - cp.predicted_yield_t_ha) < 1e-4
                assert abs(ap["predicted_water_demand_m3_ha"] - cp.predicted_water_demand_m3_ha) < 1e-4
                assert abs(ap["yield_range_lower"] - cp.yield_range_lower) < 1e-4
                assert abs(ap["yield_range_upper"] - cp.yield_range_upper) < 1e-4
                assert abs(ap["water_range_lower"] - cp.water_range_lower) < 1e-4
                assert abs(ap["water_range_upper"] - cp.water_range_upper) < 1e-4


def test_15_numerical_parity_optimize_endpoint():
    """15. Numerical parity: /api/optimize matches AquaShiftOptimizer outputs within 1e-3."""
    opt = AquaShiftOptimizer()

    test_cases = [
        OptimizationRequest(
            total_land_ha=12.0,
            water_budget_reduction_pct=20.0,
            rainfall_scenario="normal",
            optimization_mode="weighted",
            weights=OptimizationWeights(water=0.5, food=0.3, income=0.2),
        ),
        OptimizationRequest(
            total_land_ha=8.0,
            water_budget_reduction_pct=35.0,
            rainfall_scenario="deficit",
            optimization_mode="lexicographic",
            priorities=["water", "income", "food"],
        ),
    ]

    for req in test_cases:
        res = client.post("/api/optimize", json=req.model_dump())
        assert res.status_code == 200
        api_data = res.json()

        core_res = opt.optimize(req)

        # Compare solver status and KPIs
        assert api_data["solver_status"] == core_res.solver_status
        assert abs(api_data["total_water_use_m3"] - core_res.total_water_use_m3) < 1e-3
        assert abs(api_data["water_slack_m3"] - core_res.water_slack_m3) < 1e-3
        assert abs(api_data["total_food_kcal"] - core_res.total_food_kcal) < 1e-3
        assert abs(api_data["food_slack_kcal"] - core_res.food_slack_kcal) < 1e-3
        assert abs(api_data["total_net_income_inr"] - core_res.total_net_income_inr) < 1e-3
        assert abs(api_data["income_slack_inr"] - core_res.income_slack_inr) < 1e-3
        assert abs(api_data["objective_value"] - core_res.objective_value) < 1e-3

        # Compare allocations
        api_alloc = {a["crop_id"]: a["allocated_ha"] for a in api_data["allocations"]}
        core_alloc = {a.crop_id: a.allocated_ha for a in core_res.allocations}
        for cid, area in core_alloc.items():
            assert abs(api_alloc[cid] - area) < 1e-3

        # Compare diagnosis
        assert api_data["diagnosis"]["all_targets_met"] == core_res.diagnosis.all_targets_met
        assert api_data["diagnosis"]["primary_bottleneck"] == core_res.diagnosis.primary_bottleneck


def test_16_numerical_parity_stress_endpoint():
    """16. Numerical parity: /api/stress-test matches AquaShiftStressTester within 1e-3."""
    tester = AquaShiftStressTester()

    res = client.post("/api/stress-test", json={})
    assert res.status_code == 200
    api_data = res.json()

    core_res = tester.run_stress_test(request=None)

    assert api_data["strict_solve_status"] == core_res.strict_solve_status
    assert api_data["recovery_solve_status"] == core_res.recovery_solve_status
    assert api_data["individual_feasibility"] == core_res.individual_feasibility

    api_plan = api_data["closest_feasible_plan"]
    core_plan = core_res.closest_feasible_plan
    assert abs(api_plan["total_water_use_m3"] - core_plan.total_water_use_m3) < 1e-3
    assert abs(api_plan["water_slack_m3"] - core_plan.water_slack_m3) < 1e-3
    assert abs(api_plan["total_food_kcal"] - core_plan.total_food_kcal) < 1e-3
    assert abs(api_plan["food_slack_kcal"] - core_plan.food_slack_kcal) < 1e-3
    assert abs(api_plan["total_net_income_inr"] - core_plan.total_net_income_inr) < 1e-3
    assert abs(api_plan["income_slack_inr"] - core_plan.income_slack_inr) < 1e-3


def test_17_numerical_parity_sweep_endpoint():
    """17. Numerical parity: /api/simulate/sweep matches AquaShiftWaterSweep point-by-point."""
    sw = AquaShiftWaterSweep()
    req = SweepRequest(total_land_ha=10.0, rainfall_scenario="normal", start_ratio=1.0, end_ratio=0.5, step=0.1)

    res = client.post("/api/simulate/sweep", json=req.model_dump())
    assert res.status_code == 200
    api_data = res.json()

    core_res = sw.run_sweep(request=req)

    assert len(api_data["points"]) == len(core_res.points)
    assert api_data["tipping_point_water_ratio"] == core_res.tipping_point_water_ratio

    for p_api, p_core in zip(api_data["points"], core_res.points):
        assert abs(p_api["water_availability_ratio"] - p_core.water_availability_ratio) < 1e-4
        assert abs(p_api["water_budget_m3"] - p_core.water_budget_m3) < 1e-3
        assert abs(p_api["total_water_use_m3"] - p_core.total_water_use_m3) < 1e-3
        assert abs(p_api["water_slack_m3"] - p_core.water_slack_m3) < 1e-3
        assert abs(p_api["total_food_kcal"] - p_core.total_food_kcal) < 1e-3
        assert abs(p_api["food_slack_kcal"] - p_core.food_slack_kcal) < 1e-3
        assert abs(p_api["total_net_income_inr"] - p_core.total_net_income_inr) < 1e-3
        assert abs(p_api["income_slack_inr"] - p_core.income_slack_inr) < 1e-3
        assert p_api["all_targets_met"] == p_core.all_targets_met
        assert p_api["primary_bottleneck"] == p_core.primary_bottleneck


def test_18_cache_key_isolation_and_immutability():
    """18. Cache audit: Key differentiation across modes/weights/scenarios and caller mutation isolation."""
    cache = ScenarioCache(maxsize=16)

    # 1. Key differentiation across optimization modes
    req_weighted = OptimizationRequest(total_land_ha=10.0, optimization_mode="weighted")
    req_lexico = OptimizationRequest(total_land_ha=10.0, optimization_mode="lexicographic")
    key_w = cache.make_key("opt", req_weighted)
    key_l = cache.make_key("opt", req_lexico)
    assert key_w != key_l, "Different optimization modes must have distinct cache keys"

    # 2. Key differentiation across priority weights
    req_w1 = OptimizationRequest(total_land_ha=10.0, weights=OptimizationWeights(water=0.8, food=0.1, income=0.1))
    req_w2 = OptimizationRequest(total_land_ha=10.0, weights=OptimizationWeights(water=0.2, food=0.4, income=0.4))
    assert cache.make_key("opt", req_w1) != cache.make_key("opt", req_w2), "Different weights must have distinct cache keys"

    # 3. Key differentiation across rainfall scenarios
    req_norm = OptimizationRequest(total_land_ha=10.0, rainfall_scenario="normal")
    req_def = OptimizationRequest(total_land_ha=10.0, rainfall_scenario="deficit")
    assert cache.make_key("opt", req_norm) != cache.make_key("opt", req_def), "Different rainfall scenarios must have distinct cache keys"

    # 4. Key differentiation across water budgets
    req_b1 = OptimizationRequest(total_land_ha=10.0, water_budget_m3=80000.0)
    req_b2 = OptimizationRequest(total_land_ha=10.0, water_budget_m3=100000.0)
    assert cache.make_key("opt", req_b1) != cache.make_key("opt", req_b2), "Different water budgets must have distinct cache keys"

    # 5. Caller mutation isolation: modifying returned object does not taint cache
    test_obj = {"result": 42, "nested": {"alloc": 7.0}}
    cache.set("test_key", test_obj)

    retrieved_1 = cache.get("test_key")
    retrieved_1["result"] = 999
    retrieved_1["nested"]["alloc"] = -1.0

    retrieved_2 = cache.get("test_key")
    assert retrieved_2["result"] == 42, "Mutating a cached object copy must NOT corrupt subsequent cache retrievals"
    assert retrieved_2["nested"]["alloc"] == 7.0

    # 6. Post-set mutation isolation: mutating original object does not taint cache
    original_obj = {"val": [1, 2, 3]}
    cache.set("orig_key", original_obj)
    original_obj["val"].append(999)
    assert cache.get("orig_key")["val"] == [1, 2, 3]

    # 7. Thread-safety test
    def worker(idx: int):
        for i in range(50):
            k = f"k_{idx}_{i % 5}"
            cache.set(k, {"worker": idx, "i": i})
            _ = cache.get(k)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cache.size() <= 16


def test_19_sweep_monotonic_ordering_ascending_and_descending():
    """19. Sweep correctness: Monotonic ordering for both descending and ascending configurations."""
    # Descending: 1.0 down to 0.2
    res_desc = client.post(
        "/api/simulate/sweep",
        json={"total_land_ha": 10.0, "start_ratio": 1.0, "end_ratio": 0.2, "step": 0.1},
    )
    assert res_desc.status_code == 200
    points_desc = res_desc.json()["points"]
    assert len(points_desc) == 9
    ratios_desc = [p["water_availability_ratio"] for p in points_desc]
    assert ratios_desc == sorted(ratios_desc, reverse=True)
    assert ratios_desc[0] == 1.0
    assert ratios_desc[-1] == 0.2

    # Ascending: 0.2 up to 1.0
    res_asc = client.post(
        "/api/simulate/sweep",
        json={"total_land_ha": 10.0, "start_ratio": 0.2, "end_ratio": 1.0, "step": 0.1},
    )
    assert res_asc.status_code == 200
    points_asc = res_asc.json()["points"]
    assert len(points_asc) == 9
    ratios_asc = [p["water_availability_ratio"] for p in points_asc]
    assert ratios_asc == sorted(ratios_asc)
    assert ratios_asc[0] == 0.2
    assert ratios_asc[-1] == 1.0

    # Infeasibility & slack honesty
    # At ratio 0.2, water is severe; must report all_targets_met=False
    low_water_pt = points_asc[0]
    assert low_water_pt["all_targets_met"] is False
    assert low_water_pt["water_slack_m3"] > 0.0 or low_water_pt["food_slack_kcal"] > 0.0

