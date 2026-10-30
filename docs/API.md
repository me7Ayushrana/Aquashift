# AquaShift API Documentation

This document defines the complete REST API contract for the AquaShift backend.

- **Base URL:** `http://localhost:8000/api`
- **Interactive OpenAPI UI (Swagger):** `http://localhost:8000/docs`
- **ReDoc UI:** `http://localhost:8000/redoc`
- **Raw OpenAPI Specification:** `http://localhost:8000/openapi.json`
- **Offline Guarantee:** All endpoints function completely offline without external network calls or third-party API keys.

---

## 1. System Overview & Architecture

The AquaShift backend exposes a deterministic, modular pipeline:

$$\text{Data Foundation} \longrightarrow \text{ML Predictor} \longrightarrow \text{OR-Tools Optimizer} \longrightarrow \text{FastAPI REST Endpoints}$$

### Global Error Standard
All endpoints return structured JSON errors without internal Python tracebacks.

- **422 Unprocessable Entity:** Input parameter bounds violation, malformed payload, or contradictory hard constraints.
  ```json
  {
    "error": "Validation Error",
    "message": "Invalid input parameters. Please check field requirements and bounds.",
    "detail": [
      {
        "field": "total_land_ha",
        "message": "Input should be greater than 0",
        "type": "greater_than"
      }
    ]
  }
  ```
- **422 Optimization Validation Error:** Contradictory hard constraints detected pre-solve:
  ```json
  {
    "error": "Optimization Validation Error",
    "error_code": "MAX_SHARES_UNDERUTILIZE_LAND",
    "message": "Sum of maximum land shares (0.50) is strictly less than 1.00. Selected crops cannot fully utilize the available 10.0 ha.",
    "conflicting_constraints": ["max_land_shares_sum"]
  }
  ```
- **500 Internal Server Error:** Generic error wrapper ensuring zero traceback leakage.

---

## 2. Endpoints Summary

| Method | Path | Summary | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Health Check | Service status, version, and offline readiness. |
| `GET` | `/config` | Configuration | Available crops, constraints, scenarios, units, and input limits. |
| `GET` | `/baseline` | Reference Baseline | Reference Punjab/Haryana 10 ha farm baseline plan and outputs. |
| `POST` | `/predict` | ML Crop Prediction | Predicts yield (t/ha) and water demand (m³/ha) with uncertainty. |
| `POST` | `/optimize` | Crop Plan Optimization | OR-Tools GLOP LP allocation, KPI impacts, slacks, and diagnosis. |
| `POST` | `/stress-test` | Scenario Stress Test | Strict solve vs soft recovery solve with bottleneck ranking. |
| `POST` | `/simulate/sweep` | Water Availability Sweep | Parametric sweep from 100% down to 20% water availability. |

---

## 3. Endpoint Reference

### 3.1 GET `/api/health`

#### Purpose
Verifies backend operational status, version, and confirmation of offline mode.

#### Parameters
None.

#### Example Request
```bash
curl -X GET http://localhost:8000/api/health
```

#### Example Response (HTTP 200)
```json
{
  "status": "ok",
  "version": "0.1.0",
  "service": "AquaShift Backend",
  "offline_mode": true
}
```

---

### 3.2 GET `/api/config`

#### Purpose
Provides global metadata, supported crops, weather scenarios, optimization modes, input boundaries, and measurement units required by the frontend scenario builder.

#### Parameters
None.

#### Units & Validation Rules
- `crops`: 5 configured crops (`paddy`, `wheat`, `maize`, `pulses`, `millets`).
- `rainfall_scenarios`: 4 calibrated scenarios (`normal`, `deficit`, `severe_deficit`, `surplus`).
- `optimization_modes`: `weighted` and `lexicographic`.

#### Example Request
```bash
curl -X GET http://localhost:8000/api/config
```

#### Example Response (HTTP 200)
```json
{
  "region_name": "Punjab/Haryana-style paddy-wheat reference belt",
  "synthetic_data_disclosure": "Synthetic demo data calibrated to public agri statistics.",
  "crops": [
    {
      "crop_id": "paddy",
      "crop_name": "Paddy",
      "baseline_yield_t_ha": 4.8,
      "seasonal_water_m3_ha": 12500.0,
      "cultivation_cost_inr_ha": 38000.0,
      "price_inr_quintal": 2200.0,
      "calories_kcal_kg": 3600.0,
      "drought_sensitivity_ky": 1.2,
      "min_land_share": 0.0,
      "max_land_share": 0.8
    }
  ],
  "rainfall_scenarios": [
    {
      "scenario_id": "normal",
      "scenario_name": "Normal",
      "effective_rainfall_multiplier": 1.0,
      "yield_stress_multiplier": 1.0,
      "description": "Baseline historical rainfall and seasonal atmospheric demand."
    }
  ],
  "optimization_modes": ["weighted", "lexicographic"],
  "supported_priorities": ["water", "food", "income", "water_first_priority"],
  "default_land_ha": 10.0,
  "baseline_assumptions": {
    "reference_land_ha": 10.0,
    "paddy_share": 0.7,
    "maize_share": 0.3,
    "baseline_water_m3": 104127.3,
    "baseline_food_kcal": 162750000.0,
    "baseline_net_income_inr": 960136.0
  },
  "input_ranges": [
    {
      "parameter": "total_land_ha",
      "min_value": 0.1,
      "max_value": 1000.0,
      "unit": "hectares (ha)",
      "description": "Total available farm land area"
    }
  ],
  "units": {
    "land_area": "hectares (ha)",
    "yield": "tonnes per hectare (t/ha)",
    "water_demand": "cubic meters per hectare (m³/ha)",
    "food_energy": "kilocalories (kcal)",
    "monetary": "Indian Rupees (INR / ₹)"
  }
}
```

---

### 3.3 GET `/api/baseline`

#### Purpose
Returns the reference farm baseline plan, representing the traditional Punjab/Haryana allocation (70% Paddy, 30% Maize on 10.0 ha).

#### Query Parameters
- `total_land_ha` *(float, optional, default: 10.0)*: Available farm land in hectares (`gt=0.0, le=1000.0`).
- `rainfall_scenario` *(string, optional, default: "normal")*: Rainfall scenario (`normal`, `deficit`, `severe_deficit`, `surplus`).
- `water_availability_ratio` *(float, optional, default: 1.0)*: Relative water availability (`ge=0.05, le=2.0`).

#### Example Request
```bash
curl -X GET "http://localhost:8000/api/baseline?total_land_ha=10.0"
```

#### Example Response (HTTP 200)
```json
{
  "region_name": "Punjab/Haryana reference region",
  "total_land_ha": 10.0,
  "rainfall_scenario": "normal",
  "water_availability_ratio": 1.0,
  "total_water_use_m3": 104127.3,
  "total_food_kcal": 162750000.0,
  "total_gross_revenue_inr": 985110.0,
  "total_cultivation_cost_inr": 344000.0,
  "total_net_income_inr": 641110.0,
  "allocations": [
    {
      "crop_id": "paddy",
      "crop_name": "Paddy",
      "allocated_ha": 7.0,
      "land_percentage": 70.0,
      "predicted_yield_t_ha": 4.755,
      "predicted_water_demand_m3_ha": 12529.5,
      "production_tonnes": 33.285,
      "production_quintals": 332.85,
      "gross_revenue_inr": 732270.0,
      "cultivation_cost_inr": 266000.0,
      "net_income_inr": 466270.0,
      "food_calories_kcal": 119826000.0
    },
    {
      "crop_id": "maize",
      "crop_name": "Maize",
      "allocated_ha": 3.0,
      "land_percentage": 30.0,
      "predicted_yield_t_ha": 3.92,
      "predicted_water_demand_m3_ha": 5473.6,
      "production_tonnes": 11.76,
      "production_quintals": 117.6,
      "gross_revenue_inr": 252840.0,
      "cultivation_cost_inr": 78000.0,
      "net_income_inr": 174840.0,
      "food_calories_kcal": 42924000.0
    }
  ]
}
```

---

### 3.4 POST `/api/predict`

#### Purpose
Generates biophysical yield and supplementary irrigation water demand predictions across crops with indicative uncertainty margins.

#### Request Body (JSON)
- `rainfall_scenario` *(string, optional, default: "normal")*: `normal`, `deficit`, `severe_deficit`, or `surplus`.
- `water_availability_ratio` *(float, optional, default: 1.0)*: Relative irrigation ratio (`ge=0.05, le=2.0`).
- `crops` *(array of string, optional)*: Specific crop IDs. If omitted, predicts for all 5 crops.

#### Example Request
```bash
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{
    "rainfall_scenario": "deficit",
    "water_availability_ratio": 0.80
  }'
```

#### Example Response (HTTP 200)
```json
{
  "rainfall_scenario": "deficit",
  "water_availability_ratio": 0.8,
  "predictions": {
    "paddy": {
      "crop_id": "paddy",
      "crop_name": "Paddy",
      "predicted_yield_t_ha": 2.822,
      "yield_range_lower": 2.455,
      "yield_range_upper": 3.189,
      "predicted_water_demand_m3_ha": 13447.2,
      "water_range_lower": 13184.8,
      "water_range_upper": 13709.6
    },
    "wheat": {
      "crop_id": "wheat",
      "crop_name": "Wheat",
      "predicted_yield_t_ha": 2.892,
      "yield_range_lower": 2.548,
      "yield_range_upper": 3.236,
      "predicted_water_demand_m3_ha": 4839.5,
      "water_range_lower": 4614.9,
      "water_range_upper": 5064.1
    }
  },
  "units": {
    "yield": "tonnes/hectare (t/ha)",
    "water_demand": "m³/hectare",
    "water_availability_ratio": "ratio [0.05, 2.0]"
  },
  "uncertainty_note": "Error margins represent indicative validation residual spread (±1.96 * RMSE), not calibrated confidence intervals."
}
```

---

### 3.5 POST `/api/optimize`

#### Purpose
Executes deterministic OR-Tools GLOP continuous LP optimization to decide hectare allocations under competing water, food, and income constraints.

#### Request Body (JSON)
- `total_land_ha` *(float, default: 10.0)*: Available farm land area (`gt=0.0`).
- `water_budget_m3` *(float, optional)*: Explicit seasonal water budget limit in m³.
- `water_budget_reduction_pct` *(float, optional)*: Water cut relative to baseline (e.g. `20.0` for -20%).
- `food_target_kcal` *(float, optional)*: Explicit nutritional calorie target in kcal.
- `food_target_increase_pct` *(float, optional)*: Food target change relative to baseline (e.g. `10.0` for +10%).
- `income_target_inr` *(float, optional)*: Explicit net income target in INR.
- `income_target_increase_pct` *(float, optional)*: Income target change relative to baseline (e.g. `20.0` for +20%).
- `rainfall_scenario` *(string, default: "normal")*: `normal`, `deficit`, `severe_deficit`, or `surplus`.
- `water_availability_ratio` *(float, optional)*: Inferred from water budget if omitted.
- `selected_crops` *(array of string, optional)*: Allowed crop IDs (defaults to all 5).
- `optimization_mode` *(string, default: "weighted")*: `"weighted"` or `"lexicographic"`.
- `weights` *(object, optional)*: Normalized weights `{"water": 1.0, "food": 1.0, "income": 1.0}`.
- `water_first_priority` *(boolean, default: false)*: Activates lexicographic priority.

#### Example Request
```bash
curl -X POST http://localhost:8000/api/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "total_land_ha": 10.0,
    "water_budget_reduction_pct": 20.0,
    "rainfall_scenario": "normal",
    "optimization_mode": "weighted"
  }'
```

#### Example Response (HTTP 200)
```json
{
  "solver_status": "OPTIMAL",
  "optimization_mode": "weighted",
  "total_land_ha": 10.0,
  "allocations": [
    {
      "crop_id": "paddy",
      "crop_name": "Paddy",
      "allocated_ha": 4.978,
      "land_percentage": 49.78,
      "predicted_yield_t_ha": 4.755,
      "predicted_water_demand_m3_ha": 12529.5,
      "production_tonnes": 23.67,
      "production_quintals": 236.7,
      "gross_revenue_inr": 520740.0,
      "cultivation_cost_inr": 189164.0,
      "net_income_inr": 331576.0,
      "food_calories_kcal": 85212000.0
    }
  ],
  "total_water_use_m3": 61125.4,
  "water_budget_m3": 83301.8,
  "water_slack_m3": 0.0,
  "water_shortfall_pct": 0.0,
  "total_food_kcal": 126572000.0,
  "food_target_kcal": 162750000.0,
  "food_slack_kcal": 36178000.0,
  "food_shortfall_pct": 22.2,
  "total_gross_revenue_inr": 866900.0,
  "total_cultivation_cost_inr": 344000.0,
  "total_net_income_inr": 522900.0,
  "income_target_inr": 641110.0,
  "income_slack_inr": 118210.0,
  "income_shortfall_pct": 18.4,
  "binding_constraints": [],
  "local_sensitivities": [],
  "diagnosis": {
    "all_targets_met": false,
    "missed_targets": ["Food", "Income"],
    "binding_constraints": [],
    "primary_bottleneck": "Food",
    "bottleneck_ranking": [
      {
        "rank": 1,
        "dimension": "Food",
        "severity": "Moderate",
        "slack_amount": 36178000.0,
        "slack_percentage": 22.2,
        "explanation": "Moderate food caloric shortfall of 36,178,000 kcal (22.2% below target)."
      }
    ],
    "narrative_diagnosis": "Food caloric output experiences a 22.2% gap against target."
  },
  "objective_value": 0.063,
  "solve_time_ms": 1.45
}
```

---

### 3.6 POST `/api/stress-test`

#### Purpose
Executes the two-phase extreme scenario stress test:
1. Strict solve without slacks (verifies infeasibility).
2. Independent single-target and joint feasibility breakdown.
3. Soft recovery solve delivering the optimal closest-feasible diversification plan and bottleneck diagnosis.

#### Request Body (JSON)
Accepts optional `OptimizationRequest` body. If empty (`{}`), runs the reference extreme crisis scenario:
- Water budget cut: **-80%** ($20,826\text{ m}^3$)
- Food target increase: **+10%** ($179.025\text{M kcal}$)
- Income target increase: **+50%** (₹$961,665$)
- Meteorology: `severe_deficit` ($W_{\text{avail}} = 0.20$)

#### Example Request
```bash
curl -X POST http://localhost:8000/api/stress-test \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Example Response (HTTP 200)
```json
{
  "strict_solve_status": "INFEASIBLE",
  "strict_solve_message": "Standard linear programming solver failed with INFEASIBLE (compound infeasibility: Water budget independently infeasible (20,826 m³ vs min 29,892 m³); Food target independently infeasible (179,025,000 kcal vs max 19,299,400 kcal); Income target independently infeasible (₹961,665 vs max ₹-108,108)).",
  "recovery_solve_status": "OPTIMAL",
  "closest_feasible_plan": {
    "solver_status": "OPTIMAL",
    "allocations": [
      {
        "crop_id": "pulses",
        "crop_name": "Pulses",
        "allocated_ha": 5.0,
        "land_percentage": 50.0
      },
      {
        "crop_id": "millets",
        "crop_name": "Millets",
        "allocated_ha": 5.0,
        "land_percentage": 50.0
      }
    ],
    "diagnosis": {
      "primary_bottleneck": "Water",
      "bottleneck_ranking": [
        {"rank": 1, "dimension": "Water", "severity": "Critical", "slack_percentage": 43.5},
        {"rank": 2, "dimension": "Income", "severity": "High", "slack_percentage": 112.2},
        {"rank": 3, "dimension": "Food", "severity": "High", "slack_percentage": 94.9}
      ]
    }
  },
  "individual_feasibility": {
    "water": false,
    "food": false,
    "income": false
  },
  "joint_feasibility": {
    "water_and_food": false,
    "water_and_income": false,
    "food_and_income": false,
    "all_three": false
  },
  "target_boundaries": {
    "water": {"budget": 20825.5, "min_achievable": 29891.5},
    "food": {"target": 179025000.0, "max_achievable": 19299400.0},
    "income": {"target": 961665.0, "max_achievable": -108107.5}
  }
}
```

---

### 3.7 POST `/api/simulate/sweep`

#### Purpose
Generates parametric trade-off curve points across declining water availability (from 100% down to 20%), pinpointing the hydrological and economic tipping point.

#### Request Body (JSON)
- `total_land_ha` *(float, optional, default: 10.0)*: Farm land area in hectares.
- `rainfall_scenario` *(string, optional, default: "normal")*: Rainfall scenario.
- `start_ratio` *(float, optional, default: 1.0)*: Starting water ratio (`ge=0.05, le=2.0`).
- `end_ratio` *(float, optional, default: 0.20)*: Ending water ratio (`ge=0.05, le=2.0`).
- `step` *(float, optional, default: 0.10)*: Decrement step (`gt=0.0, le=1.0`).

#### Example Request
```bash
curl -X POST http://localhost:8000/api/simulate/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "total_land_ha": 10.0,
    "start_ratio": 1.0,
    "end_ratio": 0.2,
    "step": 0.1
  }'
```

#### Example Response (HTTP 200)
```json
{
  "total_land_ha": 10.0,
  "rainfall_scenario": "normal",
  "baseline_water_m3": 104127.3,
  "baseline_food_kcal": 162750000.0,
  "baseline_income_inr": 641110.0,
  "points": [
    {
      "water_availability_ratio": 1.0,
      "water_budget_reduction_pct": 0.0,
      "water_budget_m3": 104127.3,
      "total_water_use_m3": 85012.6,
      "water_slack_m3": 0.0,
      "total_food_kcal": 162750000.0,
      "food_slack_kcal": 0.0,
      "total_net_income_inr": 641110.0,
      "income_slack_inr": 0.0,
      "allocations_ha": {"paddy": 4.978, "wheat": 0.0, "maize": 2.022, "pulses": 0.0, "millets": 3.0},
      "allocations_pct": {"paddy": 49.78, "wheat": 0.0, "maize": 20.22, "pulses": 0.0, "millets": 30.0},
      "primary_bottleneck": null,
      "all_targets_met": true
    },
    {
      "water_availability_ratio": 0.9,
      "water_budget_reduction_pct": 10.0,
      "water_budget_m3": 93714.6,
      "total_water_use_m3": 73204.0,
      "water_slack_m3": 0.0,
      "total_food_kcal": 145230000.0,
      "food_slack_kcal": 17520000.0,
      "total_net_income_inr": 589400.0,
      "income_slack_inr": 51710.0,
      "allocations_ha": {"paddy": 4.0, "wheat": 0.0, "maize": 2.0, "pulses": 1.0, "millets": 3.0},
      "allocations_pct": {"paddy": 40.0, "wheat": 0.0, "maize": 20.0, "pulses": 10.0, "millets": 30.0},
      "primary_bottleneck": "Food",
      "all_targets_met": false
    }
  ],
  "tipping_point_water_ratio": 0.9,
  "tipping_point_description": "Tipping point at 90% water availability (-10% water budget): Food bottleneck emerges; farm can no longer meet baseline targets without slack."
}
```
