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
import pytest
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.optimizer import AquaShiftOptimizer

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
