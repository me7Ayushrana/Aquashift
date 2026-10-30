# Phase 4 Verification & Integration Audit Report: FastAPI Endpoints & Pipeline Integration

This report documents the verification, technical integration audit, and numerical consistency validation for **Phase 4: FastAPI Endpoints & Pipeline Integration** of AquaShift.

---

## 1. Executive Summary & Verification Gate

- **Pipeline Architecture:** Maintained strict pipeline sequence:
  $$\textbf{ML Predicts} \implies \textbf{OR-Tools Decides} \implies \textbf{AI Explains (Phase 5)}$$
- **Backend Test Suite:** **73 passed, 0 failures** across all test suites:
  - `backend/tests/test_api.py`: **25 passed** (expanded with canonical baseline regression, numerical parity, cache isolation, and sweep monotonicity tests)
  - `backend/tests/test_optimizer.py`: **22 passed**
  - `backend/tests/test_data_validation.py`: **14 passed**
  - `backend/tests/test_ml_predictor.py`: **10 passed**
  - `backend/tests/test_health.py`: **2 passed**
- **Frontend Production Build:** Clean build in 1.49s (`tsc && vite build`).
- **Live HTTP Execution:** All 7 endpoints verified via direct real HTTP requests over TCP socket (`scripts/verify_api_live.py`).
- **Dev Runner Verification:** `python scripts/dev.py` starts both backend (port 8000) and frontend (port 5173), serves requests, and terminates cleanly on SIGINT with exit code 0.
- **Offline Guarantee:** 100% offline out-of-the-box operation with zero external network requests.
- **Phases 0–3 Integrity:** Completely preserved.

---

## 2. Baseline Discrepancy Resolution & Audit Trace

### Root Cause Analysis
- In `backend/app/optimizer/model.py` (`calculate_baseline`), the canonical reference allocation has always been defined as:
  ```python
  paddy_share = 0.70
  secondary_share = 0.30
  secondary_crop = "maize" if "maize" in selected_crops else ("wheat" if "wheat" in selected_crops else selected_crops[0])
  primary_crop = "paddy" if "paddy" in selected_crops else selected_crops[-1]
  ```
  For the standard Punjab/Haryana 10 ha reference farm across all 5 crops (`["paddy", "wheat", "maize", "pulses", "millets"]`), this evaluates deterministically to:
  - **Paddy:** $7.0\text{ ha}$ ($70.0\%$ land share)
  - **Maize:** $3.0\text{ ha}$ ($30.0\%$ land share)
  - **Wheat:** $0.0\text{ ha}$ ($0.0\%$ land share)
  - **Pulses:** $0.0\text{ ha}$ ($0.0\%$ land share)
  - **Millets:** $0.0\text{ ha}$ ($0.0\%$ land share)

- Under normal reference climate ($W_{\text{avail}} = 1.0$, normal rainfall):
  - **Paddy (7.0 ha):** $7.0 \times 4.755\text{ t/ha} \times 1,000 \times 3,600\text{ kcal/kg} = 119,826,000.0\text{ kcal}$
  - **Maize (3.0 ha):** $3.0 \times 3.920\text{ t/ha} \times 1,000 \times 3,650\text{ kcal/kg} = 42,924,000.0\text{ kcal}$
  - **Total Baseline Food:** $119,826,000.0 + 42,924,000.0 = \mathbf{162,750,000.0\text{ kcal}}\text{ (162.75M kcal)}$
  - **Total Baseline Water:** $7.0 \times 12,529.5 + 3.0 \times 5,473.6 = \mathbf{104,127.3\text{ m}^3}$
  - **Total Gross Revenue:** $(332.85 \times 2,200) + (117.6 \times 2,150) = \mathbf{₹985,110.0}$
  - **Total Cultivation Cost:** $(7.0 \times 38,000) + (3.0 \times 26,000) = \mathbf{₹344,000.0}$
  - **Total Net Income:** $₹985,110.0 - ₹344,000.0 = \mathbf{₹641,110.0}$

- **Discrepancy Explanation:**
  1. The reference region is described in agricultural texts and `PROJECT_SPEC.md` as the "Punjab/Haryana-style paddy-wheat reference region". In the narrative Phase 4 report summary, the phrase "7.0 ha Paddy, 3.0 ha Wheat" was written in prose by mistake instead of "3.0 ha Maize". The underlying code in `model.py`, `baseline.py`, `stress.py`, `sweep.py`, and `test_api.py` has always implemented and asserted 3.0 ha Maize.
  2. Additionally, `backend/app/api/config.py` previously contained an outdated static placeholder for `baseline_net_income_inr` ($960,136.0$). This has been corrected by dynamically calculating `baseline_assumptions` from `AquaShiftOptimizer.calculate_baseline()`, guaranteeing 100% numerical identity with `/api/baseline` ($₹641,110.0$).
  3. A dedicated regression test (`test_13_canonical_baseline_regression_and_kpis`) now asserts the exact 7.0 ha Paddy / 3.0 ha Maize allocation and all KPI values across `/api/baseline`, `/api/config`, and the optimizer.

---

## 3. API Numerical Parity Audit

All API endpoints were audited against the underlying core Python services using floating-point tolerances ($< 10^{-4}$ for predictions, $< 10^{-3}$ for LP allocations and slacks):

| Endpoint | Core Service Function | Audit Finding & Parity Status |
| :--- | :--- | :--- |
| `POST /api/predict` | `AquaShiftPredictor.predict_all_crops` | **Exact Parity ($< 10^{-4}$):** Verified across all 5 crops and 4 rainfall scenarios. Yields, water demands, and uncertainty intervals are identical. |
| `POST /api/optimize` | `AquaShiftOptimizer.optimize` | **Exact Parity ($< 10^{-3}$):** Evaluated in both `weighted` and `lexicographic` modes. Solver status, allocated hectares, water/food/income totals, slack shortfalls, and bottleneck diagnosis match down to 3 decimal places. |
| `GET /api/baseline` | `AquaShiftOptimizer.calculate_baseline` | **Exact Parity ($< 10^{-3}$):** Crop areas, percentages, and all 5 financial/physical KPIs match exactly. |
| `POST /api/stress-test` | `AquaShiftStressTester.run_stress_test` | **Exact Parity ($< 10^{-3}$):** Strict solve infeasibility detection, recovery solve optimality, individual feasibility bounds, and bottleneck ranking match completely. |
| `POST /api/simulate/sweep` | `AquaShiftWaterSweep.run_sweep` | **Exact Parity ($< 10^{-3}$):** All 9 trade-off curve points, crop area allocations, water usage, slacks, and dynamic tipping point ratio match point-by-point. |

---

## 4. Scenario Caching Audit (`backend/app/core/cache.py`)

A comprehensive audit of `ScenarioCache` verified:
1. **Key Differentiation Across Modes & Parameters:**
   - Optimization modes (`weighted` vs `lexicographic`) generate distinct SHA-256 keys.
   - Priority weights (`{"water": 0.8, ...}` vs `{"water": 0.2, ...}`) generate distinct SHA-256 keys.
   - Rainfall scenarios (`normal` vs `deficit`) generate distinct SHA-256 keys.
   - Water budgets (`100,000` vs `80,000` m³) generate distinct SHA-256 keys.
   - Crop selection order (`["paddy", "maize"]` vs `["maize", "paddy"]`) is normalized before hashing to avoid spurious misses.
2. **Caller Immutability via Deep Copying:**
   - Both `get()` and `set()` apply `copy.deepcopy()`.
   - Mutating a response object returned by `cache.get()` has zero side-effects on subsequent cache retrievals.
   - Mutating an original object after calling `cache.set()` does not alter the cached copy.
3. **Thread Safety:**
   - Guarded with `threading.Lock()` across all cache operations (`get`, `set`, `clear`, `size`).
   - Verified clean execution under concurrent multi-threaded read/write workloads without deadlock or race conditions.

---

## 5. Water Sweep Simulation Correctness (`backend/app/optimizer/sweep.py`)

1. **Monotonic Ordering:**
   - Supports both descending sweeps (e.g. `1.0` down to `0.20` in steps of `0.10`) and ascending sweeps (e.g. `0.20` up to `1.00`).
   - All points are guaranteed strictly monotonic in the requested order.
2. **Water Budget Binding:**
   - Each point's water budget is precisely bound: $B_w = \text{round}(B_{\text{baseline}} \times \text{ratio}, 1)$.
3. **Honest Infeasibility Reporting:**
   - Infeasible points are never masked or substituted.
   - When water availability is insufficient (e.g. at 20%), the solver reports `all_targets_met = False`, outputs positive slack values for unmet targets, and correctly identifies primary bottlenecks.
4. **Dynamic Tipping Point Detection:**
   - Evaluated directly from solver results (`res.diagnosis.all_targets_met`), not hardcoded thresholds.
   - Identifies the exact water availability ratio (e.g. 90% water availability / -10% water budget) where farm outputs first fail to satisfy baseline targets without slack.

---

## 6. Full Test Suite Breakdown (73 Passed)

### API Integration & Audit Tests (`backend/tests/test_api.py` — 25 Tests)
1. `test_api_health_endpoint`: HTTP 200, status "ok", version, offline mode.
2. `test_api_config_endpoint`: HTTP 200, 5 crops, 4 weather scenarios, input ranges, units.
3. `test_api_baseline_endpoint`: HTTP 200, 10 ha, 162.75M kcal food, ₹641,110 net income.
4. `test_api_predict_endpoint`: HTTP 200, yield and water demand for 5 crops with error bounds.
5. `test_api_optimize_endpoint_weighted`: HTTP 200, optimal status, land conservation, diagnosis.
6. `test_api_optimize_endpoint_lexicographic`: HTTP 200, lexicographic priority mode.
7. `test_1_invalid_land_area`: HTTP 422 for `total_land_ha <= 0`.
8. `test_2_invalid_rainfall_scenario`: HTTP 422 for unknown weather scenarios on predict and optimize.
9. `test_3_invalid_optimization_mode`: HTTP 422 for unknown optimization solver mode.
10. `test_4_negative_water_budget`: HTTP 422 for negative water budget.
11. `test_5_malformed_request_payload`: HTTP 422 for non-JSON or malformed payload.
12. `test_6_optimizer_hard_constraint_failure`: HTTP 422 with structured diagnostics (`MAX_SHARES_UNDERUTILIZE_LAND`).
13. `test_7_extreme_drought_stress_test_response`: Strict solve INFEASIBLE, recovery solve OPTIMAL, Water Critical, Income High, Food High.
14. `test_8_consistency_predict_and_optimize`: Verified predictions from `/api/predict` match `/api/optimize` crop metrics.
15. `test_9_consistency_baseline_and_calculations`: Verified `/api/baseline` matches internal `calculate_baseline` outputs.
16. `test_10_sweep_output_ordered_and_valid`: Monotonically decreasing ratios, valid numeric totals, tipping point detection.
17. `test_11_cache_hit_on_identical_request`: Identical optimization requests return identical cached outputs.
18. `test_12_docs_and_openapi_endpoints`: Verified `/docs` and `/openapi.json` are accessible.
19. `test_13_canonical_baseline_regression_and_kpis`: Regression verifying 7.0 ha Paddy + 3.0 ha Maize and exact KPIs across API and optimizer.
20. `test_14_numerical_parity_predict_endpoint`: Verified parity within $< 10^{-4}$ between `/api/predict` and `AquaShiftPredictor`.
21. `test_15_numerical_parity_optimize_endpoint`: Verified parity within $< 10^{-3}$ between `/api/optimize` and `AquaShiftOptimizer`.
22. `test_16_numerical_parity_stress_endpoint`: Verified parity within $< 10^{-3}$ between `/api/stress-test` and `AquaShiftStressTester`.
23. `test_17_numerical_parity_sweep_endpoint`: Verified parity within $< 10^{-3}$ point-by-point between `/api/simulate/sweep` and `AquaShiftWaterSweep`.
24. `test_18_cache_key_isolation_and_immutability`: Verified cache key uniqueness across modes/weights/scenarios and deep-copy caller isolation.
25. `test_19_sweep_monotonic_ordering_ascending_and_descending`: Verified monotonic ordering for both descending and ascending configurations.

### Core Modules Test Breakdown (48 Tests)
- `backend/tests/test_optimizer.py`: 22 passed (land conservation across scales, slacks, rankings, food classification rules, feasibility boundaries).
- `backend/tests/test_data_validation.py`: 14 passed (crop bounds, weather scenarios, FAO-56 monotonicity, water ordering).
- `backend/tests/test_ml_predictor.py`: 10 passed (model inference, non-negativity, feature validation, dual split metrics).
- `backend/tests/test_health.py`: 2 passed (health and root endpoints).

---

## 7. Remaining Limitations

1. **Static Pricing Horizon:** Crop prices reflect minimum support prices (MSP) without real-time intraday market volatility.
2. **Single-Season Planning Horizon:** Hydrological feedback is modeled for the seasonal planning period; multi-year aquifer recharge depletion is not modeled dynamically.
3. **Indicative Calibration:** All parameters are synthetic demo calibrations to public statistics, not verified field-level extension guidelines.
