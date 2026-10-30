# AquaShift

**Tagline:** Plan crops. Balance water. Protect livelihoods.  
**Hackathon:** Zinnovatio 4.0 — AgriTech & Rural Transformation  
**Team:** NullPointers (Jaideep Singh, Gurnoor Kaur, Shekhar Sharma, Yashika Chandel, Ayush Rana)  
**Product:** Water-constrained crop planning and diversification decision simulator.

---

## Disclosure

> **Synthetic demo data calibrated to public agri statistics.**  
> Baseline values, water requirements, and crop parameters are calibrated from public datasets (e.g. ICAR, CGWB, CACP) as indicative scenario models for the Punjab/Haryana paddy-wheat belt. They illustrate the decision framework and do not constitute district-level agronomic advisories.

---

## 1. Product Vision & Architecture

AquaShift provides the missing decision layer for agriculture under competing constraints.

- **ML Predicts:** scikit-learn models predict yield response and water demand under drought/rainfall scenarios using FAO-56 crop-water equations.
- **Optimization Decides:** Google OR-Tools GLOP linear programming determines continuous hectare allocations under land, agronomic, and target limits.
- **AI Explains:** Claude (or deterministic template fallbacks) translates numerical results into plain-language summaries for farmers and district planners. The LLM never computes or alters numbers.
- **Stress-Test Recovery:** Extreme stress scenarios diagnose bottlenecks (Water Critical, Income High, Food Moderate) and return the closest-feasible plan rather than an unhelpful `INFEASIBLE` error.

---

## 2. Six-Stage Pipeline

1. **Scenario** — Land, water budget, crop selection, food and income targets, rainfall scenario.
2. **ML Predictor** — Predicts yield and water demand with uncertainty intervals.
3. **Optimizer** — Solves continuous crop allocation via OR-Tools GLOP.
4. **Stress Test** — Evaluates feasibility, slacks, and diagnoses bottlenecks.
5. **AI Insight** — Plain-language farmer/planner summary, verified against solver JSON.
6. **Crop Plan** — Water, food, and farmer income KPI impact dashboard.

---

## 3. Technology Stack

- **Backend:** Python 3.11, FastAPI, Pydantic v2, Uvicorn, OR-Tools, scikit-learn, joblib, pandas, pytest.
- **Frontend:** React, Vite, TypeScript, Tailwind CSS, Recharts.
- **Optional LLM:** Anthropic Python SDK (with deterministic template offline mode).

---

## 4. Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm

### Local Development

Run both backend and frontend with a single command:

```bash
python scripts/dev.py
```

Or run them individually:

#### Backend
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uvicorn backend.app.main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173` and the backend OpenAPI documentation is available at `http://localhost:8000/docs`.

---

## 5. Agricultural Data Foundation & Reproducibility

AquaShift uses a calibrated synthetic agricultural dataset for the Punjab/Haryana-style reference region (`Paddy, Wheat, Maize, Pulses, Millets`) across four climate scenarios (`Normal, Deficit, Severe Deficit, Surplus`).

### Datasets:
- **`data/crops.csv`**: Crop baselines (yield, seasonal water demand, cultivation costs, MSP prices, caloric densities, and FAO-56 $K_y$ drought sensitivities).
- **`data/weather_scenarios.csv`**: Effective rainfall and yield stress multipliers across four meteorological scenarios.
- **`data/training_data.csv`**: 2,000 synthetic observations generated via FAO-56 crop-water equations ($Y_a / Y_m = 1 - K_y(1 - ET_a/ET_m)$) with controlled noise maintaining physical monotonicity.
- **`data/ASSUMPTIONS.md`**: Complete documentation of indicative assumptions, sources (CACP, ICAR, CGWB), parameter units, and limitations.
- **`data/loaders/`**: Documented, typed integration interfaces for external public datasets (`data.gov.in`, `ICAR`, `IMD`, `CGWB`, `Agmarknet`, `APEDA`).

### Data Generation Command:
```bash
python scripts/generate_data.py --seed 42
```

### Reproducibility Verification:
The dataset generation is fully deterministic. With seed `42`, the SHA-256 hash of `data/training_data.csv` is:
```text
965c6588376038cb4fc7ef44a44c775b887532f63936078b3dff3a68a9925c02
```

---

## 6. Machine Learning Predictor (Phase 2)

AquaShift employs two specialized, physically-bounded `HistGradientBoostingRegressor` estimators:

1. **Yield Predictor (`actual_yield_t_ha`):**
   - **Features:** `[baseline_yield_t_ha, drought_sensitivity_ky, yield_stress_multiplier, effective_rainfall_multiplier, water_availability_ratio]`
   - **Monotonic Constraint:** `monotonic_cst=[1, 0, 1, 1, 1]`. Mathematically guarantees that predicted yield never decreases when irrigation water availability increases ($\frac{\partial \hat{Y}}{\partial W_{\text{avail}}} \ge 0$).
   - **Synthetic Validation Metrics:** MAE = 0.0720 t/ha, RMSE = 0.0943 t/ha, $R^2 = 0.9944$.

2. **Water Demand Predictor (`water_demand_m3_ha`):**
   - **Features:** `[seasonal_water_m3_ha, effective_rainfall_multiplier]`
   - **Independence:** Excludes `water_availability_ratio` because crop water demand represents required irrigation, independent of quota availability.
   - **Monotonic Constraint:** `monotonic_cst=[1, -1]`. Guarantees higher rainfall decreases supplementary irrigation need.
   - **Synthetic Validation Metrics:** MAE = 66.52 m³/ha, RMSE = 98.88 m³/ha, $R^2 = 0.9992$.

### Model Training Command:
```bash
python scripts/train_model.py --seed 42
```
Artifacts are saved in `backend/app/ml/artifacts/` (`yield_model.joblib`, `water_demand_model.joblib`, `metrics.json`).


