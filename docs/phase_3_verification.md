# Phase 3 Verification Report: OR-Tools Optimization Engine & Food Diagnosis Audit

This report records the complete verification of **Phase 3: OR-Tools Optimization Engine**, including the final technical audit of food severity classification, unit consistency, and extreme-scenario stress recovery.

---

## 1. Executive Summary & Verification Status

- **Optimizer Status:** Production-ready deterministic Linear Programming (LP) engine using Google OR-Tools `pywraplp` (GLOP solver).
- **Backend Test Suite:** **48 passed, 0 failures** across all modules:
  - `backend/tests/test_data_validation.py`: 14 passed
  - `backend/tests/test_health.py`: 2 passed
  - `backend/tests/test_ml_predictor.py`: 10 passed
  - `backend/tests/test_optimizer.py`: 22 passed
- **Frontend Production Build:** Clean build in 1.41s (`dist/assets/index-CwEeOXq-.js` 156.37 kB, gzip: 49.93 kB).
- **Extreme Scenario Verification:** Confirmed independent infeasibility reporting for strict solve and valid optimal recovery plan under severe drought (-80% water, +10% food, +50% income).

---

## 2. Food Severity Classification Rules & Decoupling

### Audit Finding
Previously, `backend/app/optimizer/diagnosis.py` contained a heuristic branch where food severity was downgraded to `"Moderate"` whenever farm net income was negative (`income_achieved_inr < 0`), under the assumption that any positive grain production offered survival sustenance during an economic crisis. This caused a catastrophic food shortfall of 94.9% (169.83M kcal gap) in the severe drought stress test to be classified as `"Moderate"`, understating severe nutritional insecurity.

### Corrected Mathematical Rules
Food severity is now 100% decoupled from farm income and purely derived from normalized percentage shortfall against the food target:

$$\text{food\_slack\_pct} = \frac{\text{food\_slack\_kcal}}{\text{food\_target\_kcal}} \times 100.0$$

| Classification | Mathematical Condition | Interpretation |
| :--- | :--- | :--- |
| **Satisfied** | $\text{food\_slack\_kcal} \le 1,000.0\text{ kcal}$ | Target caloric production is fully met within numerical tolerance. |
| **High** | $\text{food\_slack\_pct} \ge 50.0\%$ | Substantial nutritional deficit: farm output is less than half of target calories. |
| **Moderate** | $0.0\% < \text{food\_slack\_pct} < 50.0\%$ | Noticeable caloric gap, but more than 50% of target energy is delivered. |

*Crucial Invariant:* Food severity is **never** downgraded because income is negative. Both Water and Income dimensions remain independently derived.

### Rank Score Formulation
All bottleneck dimensions are ranked using a continuous composite score:

$$\text{rank\_score} = (\text{severity\_weight} \times 1,000) + (500 \text{ if physical\_barrier else } 0) + \min(\text{slack\_pct}, 100.0)$$

Where severity weights are: `Critical = 4`, `High = 3`, `Moderate = 2`, `Satisfied = 1`.

### Edge-Case Test Suite (`test_18_food_severity_classification_rules`)
Automated tests verify all 5 required boundary conditions:
1. **10% Shortfall:** Severity is `Moderate` (Rank score: $2000 + 10.0 = 2010.0$).
2. **50% Shortfall:** Severity is `High` (Rank score: $3000 + 50.0 = 3050.0$).
3. **95% Shortfall:** Severity is `High` (Rank score: $3000 + 95.0 = 3095.0$).
4. **95% Shortfall with Negative Net Income (₹-150,000):** Severity is strictly preserved as `High` (Rank score: $3000 + 95.0 = 3095.0$).
5. **All Targets Satisfied:** All dimensions are `Satisfied`, `primary_bottleneck` is `None`, and slack is zero.

---

## 3. End-to-End Food Unit & Feasibility Boundary Audit

### Unit Consistency Check
Every stage of the AquaShift pipeline uses the exact same physical caloric unit:

$$\text{Food production (kcal)} = \text{crop area (ha)} \times \text{yield (tonnes/ha)} \times 1,000\text{ (kg/tonne)} \times \text{calories (kcal/kg)}$$

| Component | File Reference | Unit / Formula |
| :--- | :--- | :--- |
| **Crop Attributes** | `data/crops.csv` | `calories_kcal_kg` in kcal per kg (e.g. Paddy: 3600, Wheat: 3400, Maize: 3650, Pulses: 3450, Millets: 3300). |
| **ML Predictions** | `backend/app/ml/predictor.py` | `predicted_yield_t_ha` in metric tonnes per hectare. |
| **Baseline Metrics** | `backend/app/optimizer/model.py` | `b_food += tonnes * 1000.0 * cal` (kcal). |
| **Target Setting** | `backend/app/optimizer/model.py` | `food_target_kcal = baseline * (1 + pct / 100)` (kcal). |
| **LP Objective / Constraints** | `backend/app/optimizer/model.py` | `food_coeffs[c] = y * 1000.0 * cal` (kcal/ha), `food_expr + s_f >= food_target_kcal`. |
| **Slack / Output Accounting** | `backend/app/optimizer/model.py` | `c_food = round(prod_tonnes * 1000.0 * cal, 1)` (kcal), `val_sf = max(0, target - tot_food)`. |
| **Feasibility Boundaries** | `backend/app/optimizer/stress.py` | $\max \sum x_c \cdot (Y_c \times 1000 \times \text{cal}_c)$ (kcal). |
| **API Schemas** | `backend/app/models/schemas.py` | `total_food_kcal`, `food_target_kcal`, `food_slack_kcal` (float, kcal). |

### Mathematical Reconciliation: 162.75M kcal Baseline vs 19.30M kcal Drought Maximum

#### 1. Normal Reference Baseline (162.75M kcal)
For the 10.0 ha reference Punjab/Haryana farm under normal conditions ($W_{\text{avail}} = 1.0$, normal rainfall):
- **Paddy (7.0 ha):** $7.0 \times 4.755\text{ t/ha} \times 1,000 \times 3,600\text{ kcal/kg} = 119,826,000\text{ kcal}$
- **Maize (3.0 ha):** $3.0 \times 3.920\text{ t/ha} \times 1,000 \times 3,650\text{ kcal/kg} = 42,924,000\text{ kcal}$
- **Total Baseline Food:** $119,826,000 + 42,924,000 = \mathbf{162,750,000.0\text{ kcal}}\text{ (162.75M kcal)}$
- **Target at +10% Security:** $162.75\text{M} \times 1.10 = \mathbf{179,025,000.0\text{ kcal}}\text{ (179.025M kcal)}$

#### 2. Severe Drought Maximum Achievable Food (19.30M kcal)
Under severe deficit ($W_{\text{avail}} = 0.20$, severe deficit rainfall), severe water stress depresses yields across all crops:
- **Wheat ($k_y = 1.00$):** $Y = 0.587\text{ t/ha} \implies \text{food\_coeff} = 0.587 \times 1000 \times 3400 = \mathbf{1,995,800\text{ kcal/ha}}$
- **Millets ($k_y = 0.65$):** $Y = 0.505\text{ t/ha} \implies \text{food\_coeff} = 0.505 \times 1000 \times 3300 = \mathbf{1,666,500\text{ kcal/ha}}$
- **Maize ($k_y = 1.15$):** $Y = 0.050\text{ t/ha} \implies \text{food\_coeff} = 0.050 \times 1000 \times 3650 = \mathbf{182,500\text{ kcal/ha}}$
- **Paddy ($k_y = 1.20$):** $Y = 0.050\text{ t/ha} \implies \text{food\_coeff} = 0.050 \times 1000 \times 3600 = \mathbf{180,000\text{ kcal/ha}}$
- **Pulses ($k_y = 0.85$):** $Y = 0.050\text{ t/ha} \implies \text{food\_coeff} = 0.050 \times 1000 \times 3450 = \mathbf{172,500\text{ kcal/ha}}$

To maximize caloric output subject to agronomic share caps:
- Wheat is capped at $80\%$ max share $\implies 8.00\text{ ha} \times 1,995,800 = 15,966,400\text{ kcal}$.
- The remaining $2.00\text{ ha}$ goes to Millets (cap 50%) $\implies 2.00\text{ ha} \times 1,666,500 = 3,333,000\text{ kcal}$.
- **Analytical Maximum Feasible Food:** $15,966,400 + 3,333,000 = \mathbf{19,299,400.0\text{ kcal}}\text{ (19.30M kcal)}$.

#### 3. Why the Drought Maximum is 88.1% Below Baseline
1. **Severe Biophysical Yield Loss:** Severe drought causes $74.3\%$ yield loss in hardy millets and up to $98.9\%$ loss in thirsty paddy/maize.
2. **Caloric Energy Collapse:** Caloric density per hectare drops from $17.12\text{M kcal/ha}$ (normal paddy) down to at most $2.00\text{M kcal/ha}$ (drought wheat).
3. **Physical Impossibility:** Even allocating $100\%$ of the land exclusively to the top two caloric producers yields only $19.30\text{M kcal}$. Therefore, the $+10\%$ food target ($179.025\text{M kcal}$) is **independently physically infeasible** under severe drought by a margin of $159.73\text{M kcal}$ ($89.2\%$ shortfall).

---

## 4. Extreme Scenario Stress-Test Verification

Executing `AquaShiftStressTester.run_stress_test()` under $-80\%$ water budget ($20,826\text{ m}^3$), $+10\%$ food ($179.025\text{M kcal}$), and $+50\%$ income (₹$961,665$):

### Phase 1: Independent Feasibility Audit & Strict Solve
- **Strict Solve Status:** `INFEASIBLE`
- **Audit Findings:**
  - Water budget is **independently infeasible**: Available $20,826\text{ m}^3$ vs minimum possible $29,892\text{ m}^3$.
  - Food target is **independently infeasible**: Target $179,025,000\text{ kcal}$ vs maximum possible $19,299,400\text{ kcal}$.
  - Income target is **independently infeasible**: Target ₹$961,665$ vs maximum possible ₹$-108,108$.
  - All joint pairs and triplet are strictly infeasible.

### Phase 2: Soft Recovery Solve
- **Recovery Status:** `OPTIMAL`
- **Optimal Allocations:**
  - Paddy: $0.00\text{ ha}$ ($0.0\%$)
  - Wheat: $0.00\text{ ha}$ ($0.0\%$)
  - Maize: $0.00\text{ ha}$ ($0.0\%$)
  - Pulses: $5.00\text{ ha}$ ($50.0\%$)
  - Millets: $5.00\text{ ha}$ ($50.0\%$)
- **Achieved Metrics & Slacks:**
  - **Water:** $29,891.5\text{ m}^3$ used vs $20,825.5\text{ m}^3$ budget $\implies \text{slack} = 9,066.0\text{ m}^3$ ($43.5\%$ over budget).
  - **Food:** $9,195,000\text{ kcal}$ achieved vs $179,025,000\text{ kcal}$ target $\implies \text{slack} = 169,830,000\text{ kcal}$ ($94.9\%$ shortfall).
  - **Income:** ₹$-116,862.5$ achieved vs ₹$961,665.0$ target $\implies \text{slack} = ₹1,078,527.5$ ($112.2\%$ shortfall).
- **Corrected Bottleneck Ranking:**
  1. **Rank 1: Water** | `Critical` | $43.5\%$ deficit ($9,066\text{ m}^3$) | Rank score: $4543.5$
  2. **Rank 2: Income** | `High` | $112.2\%$ deficit (₹$1,078,528$) | Rank score: $3600.0$
  3. **Rank 3: Food** | `High` | $94.9\%$ deficit ($169,830,000\text{ kcal}$) | Rank score: $3594.9$

Food severity is correctly reported as **`High`**, properly reflecting severe nutritional insecurity alongside farm economic distress.

---

## 5. Architectural Invariants & Limitations

1. **Synthetic Data Calibration:** All data values and ML predictions represent synthetic demonstration assumptions calibrated to public statistics for a stylized Punjab/Haryana paddy-wheat region, not verified field-level measurements.
2. **Linear Continuous Modeling:** GLOP continuous LP decision variables are used. Discrete farm constraints (e.g. minimum equipment plot sizes or binary crop selection) are not modeled.
3. **Decoupled Severity Logic:** All severity classifications (Water, Food, Income) are computed through pure mathematical formulas based on physical boundary feasibility and normalized slack percentages, with zero scenario-specific flags or hardcoded labels.
