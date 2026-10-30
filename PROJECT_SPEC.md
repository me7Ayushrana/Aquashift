# AquaShift — Project Specification

**Project:** AquaShift  
**Tagline:** Plan crops. Balance water. Protect livelihoods.  
**Hackathon:** Zinnovatio 4.0 — AgriTech & Rural Transformation  
**Team:** NullPointers  
**Product type:** Water-constrained crop planning and diversification simulator  
**Default reference region:** Punjab/Haryana-style paddy-wheat belt (configurable)

---

## 1. Product identity and purpose

AquaShift is a decision-support simulator that helps farmers, FPOs, district planners, cooperatives, and agribusinesses compare crop allocations under competing water, food-production, and farmer-income constraints.

### Core question

> Given limited water, what should we grow instead, and what will it cost in food and farmer income?

Existing agricultural tools may provide information, advisories, satellite observations, or market data. AquaShift is intended to provide the decision layer that evaluates crop choices under explicit constraints.

### Product principles

1. **ML predicts.** It estimates crop yield and water demand under scenario conditions.
2. **Optimization decides.** OR-Tools determines crop-area allocations.
3. **AI explains.** The optional LLM explains the numerical plan; it never calculates, edits, or invents values.
4. The application must work without an LLM key, using deterministic templates.
5. Extreme scenarios must return a closest-feasible plan with slack and a bottleneck diagnosis, never a bare `INFEASIBLE` result to the user.
6. Synthetic demo data must be clearly labelled in the README and visible UI footer.

---

## 2. Users

- Farmers and Farmer Producer Organization (FPO) members planning collectively.
- District and regional planners evaluating diversification and water-policy scenarios.
- FPOs and cooperatives planning seasonal crop allocation.
- Agribusinesses planning supply under climate and water constraints.

The interface must use simple language, readable large type, clear visual hierarchy, high contrast, and responsive layouts suitable for mobile devices.

---

## 3. Required technology stack

Do not substitute technologies without explicit approval.

### Backend

- Python 3.11
- FastAPI
- Pydantic v2
- Uvicorn
- OR-Tools (`pywraplp` with GLOP linear solver)
- scikit-learn
- joblib
- pandas
- pytest

### Frontend

- React
- Vite
- TypeScript
- Tailwind CSS
- Recharts

### Optional LLM

- Python `anthropic` SDK
- Model configured through `ANTHROPIC_MODEL`
- API key configured through optional `ANTHROPIC_API_KEY`

### Persistence and deployment constraints

- No database. Use CSV and JSON files.
- No authentication or accounts.
- No microservices.
- No secrets committed to the repository.
- Provide `.env.example`.
- Pin dependency versions in `requirements.txt` and `package.json`.
- Provide cross-platform Python/npm scripts; do not depend on bash-only commands or `make`.

---

## 4. User inputs and scenario configuration

The scenario builder must support:

1. **Land:** available area in hectares.
2. **Water budget:** available water, with a percentage-change slider relative to baseline.
3. **Crop selection:** Paddy, Wheat, Maize, Pulses, and Millets. Crop list must be extensible through configuration.
4. **Food target:** percentage-change slider.
5. **Income target:** percentage-change slider.
6. **Rainfall scenario:** Normal, Deficit, Severe Deficit, or Surplus.
7. **Optimization mode:** weighted priorities or lexicographic priorities.
8. **Priority controls:** Water, Food, and Income priority sliders, plus a “Water first” toggle (Tier 2).

Validate all inputs with sensible bounds and return clear validation messages.

---

## 5. Required pipeline

Show an animated six-step pipeline in the UI:

1. **Scenario** — land, water, targets, crop choices, and climate.
2. **ML predictor** — yield and water-use effects.
3. **Optimizer** — crop allocation using OR-Tools.
4. **Stress test** — finds bottlenecks when targets conflict.
5. **AI insight** — explains the result in plain language.
6. **Crop plan** — water, food, and income impact.

The UI must communicate the division of responsibility: ML predicts, optimization decides, AI explains.

---

## 6. Tier 1 — Must-have features

### 6.1 Scenario builder

Implement all inputs listed in Section 4, including crop selection and rainfall scenario.

### 6.2 Baseline plan

Create a realistic, paddy-heavy baseline crop allocation for the configurable Punjab/Haryana-style paddy-wheat reference region.

Baseline values and all other assumed numerical values must be documented in `data/ASSUMPTIONS.md`. These values are indicative demo assumptions, not verified district recommendations.

### 6.3 OR-Tools optimizer

Use OR-Tools GLOP linear programming with continuous hectare decision variables, one variable per selected crop.

#### Hard constraints

- Total allocated area must not exceed available land.
- Per-crop minimum and maximum land-share/agronomic/rotation limits must be enforced.
- The application must never return an allocation that violates hard constraints.

#### Soft constraints

Represent these with non-negative slack variables:

- Water use must be less than or equal to the available water budget.
- Food production must be greater than or equal to the food target.
- Net farmer income must be greater than or equal to the income target.

#### Objective

- Minimize weighted, normalized slack.
- Include a small tie-breaker that minimizes water use.
- Support **weights mode**, with Water/Food/Income priority sliders.
- Support **lexicographic mode**, solving sequentially in this order: Water → Food → Income.

The exact normalization, weighting, and sequential-solve mechanics must be documented and tested. Do not hide trade-offs in unexplained constants.

#### Optimizer response

Return typed, traceable values including:

- Solver status.
- Crop allocation in hectares.
- Percentage of total land per crop.
- Allocation delta versus baseline.
- Water use versus budget and percentage gap.
- Food production versus target and percentage gap.
- Net income versus target and percentage gap.
- Slack values for each soft constraint.
- Binding constraints.
- Shadow prices where available and meaningful.
- Illustrative interpretation such as the value of one additional m³ of water in ₹, clearly labelled as a local model sensitivity rather than a guaranteed market value.
- Solve time.

Every displayed numerical output must originate from the predictor or optimizer. Do not let the LLM supply or alter numeric values.

### 6.4 Before/after comparison

Display baseline and optimized allocations side by side using stacked bars or donut charts.

Show three KPI cards:

- Water
- Food
- Income

Each KPI must include:

- Current result.
- Baseline comparison.
- Percentage change versus baseline.
- Gap versus target.
- Green/amber/red status with an understandable legend.

### 6.5 Extreme-scenario stress test

Run the defined extreme scenario:

- Water availability: −80%.
- Income target: +50%.
- Food target: +10%.

The system must:

1. Run a strict solve to identify whether all strict targets can be met.
2. If strict constraints are infeasible, run a recovery solve with non-negative slack variables.
3. Return the closest-feasible allocation while preserving hard constraints.
4. Diagnose and rank bottlenecks using relative slack size and shadow-price information where available.
5. Tune the demo assumptions so the expected ranking is:
   - Water: **Critical**
   - Income: **High**
   - Food: **Moderate**
6. Document the tuned assumptions and ranking method.

The UI must show a comparison:

- “Standard solver says: INFEASIBLE” (only when the strict solve actually is infeasible).
- “AquaShift: closest feasible plan + bottleneck diagnosis”.

Do not label the recovery solve itself as infeasible if it successfully returns a plan. If the model cannot find a plan satisfying hard constraints, return a clear structured error explaining that no allocation is possible under the hard agronomic/land rules, with diagnostic details. Never fabricate a plan.

### 6.6 ML predictor

Train a scikit-learn model to predict, per crop:

- Yield in tonnes per hectare.
- Water demand under rainfall and water-stress scenarios.

Generate a seeded synthetic training dataset based on agronomic relationships, including a FAO-style yield-response-to-water relationship:

`Ya / Ym = 1 − Ky × (1 − ETa / ETm)`

Include controlled noise while preserving sensible physical bounds and monotonic behaviour.

Requirements:

- Fixed random seeds.
- Reproducible training script: `scripts/train_model.py`.
- Data generation script: `scripts/generate_data.py`.
- Persist model artifacts using joblib.
- Return simple uncertainty ranges, such as quantiles or ensemble spread.
- Test that predicted yield does not increase as water stress worsens, all else equal.
- Clearly disclose that synthetic-data predictions are indicative and require local calibration.

### 6.7 AI insight

Claude may explain the optimizer's JSON output in plain language.

Audience modes:

- `farmer`
- `planner`

The explanation must be under 180 words and include:

- Headline.
- What changes in the crop plan.
- What it costs or gains.
- Biggest risk.
- Next steps.

Strict rules:

- LLM must not calculate, invent, round into unsupported claims, or change numbers.
- Provide the numerical plan first; load the explanation lazily so the UI never blocks on the LLM.
- Validate every numeric claim in the explanation against the plan JSON, using a documented rounding tolerance and conservative parsing.
- If validation fails, discard the generated explanation and use a deterministic template.
- If no API key is configured, use the deterministic template.
- The offline application must remain fully usable.

### 6.8 One-click Demo Mode

Provide a one-click demo with captions that automatically plays the exact two-minute story:

1. Show baseline plan.
2. Reduce water by 20%.
3. Run optimization.
4. Show new allocation and impact.
5. Load the extreme scenario.
6. Run stress test.
7. Show bottleneck diagnosis.
8. Show AI explanation.

Demo values and transitions must be deterministic and reproducible. Users must be able to reset or exit demo mode.

---

## 7. Tier 2 — Should-have features

Only begin after Tier 1 is implemented and verified.

1. **Water sweep chart:** simulate water from 0% to −80% in steps; plot income, food, and paddy area; identify and mark a tipping point using a documented rule.
2. **Priority sliders:** Water, Food, and Income.
3. **Water-first toggle:** provide a clear mapping to optimization priorities or lexicographic mode.
4. **Relaxation suggestions:** use additional solver runs to calculate items such as minimum extra water required to meet income target and maximum achievable income at current water. Never use the LLM for these calculations.
5. **English/Hindi toggle:** translate UI strings and AI explanations.
6. **Verified insight badge:** display “Numbers verified against optimizer ✓” only when numeric validation passes or a deterministic template is used with trusted plan data.
7. **Uncertainty ranges:** show ML prediction uncertainty in the UI.

---

## 8. Tier 3 — Nice-to-have features

Only begin if Tier 1 and Tier 2 are stable and there is sufficient time.

1. One-page PDF export.
2. CSV export.
3. Read-aloud using Web Speech API.
4. Shareable scenario links through URL parameters.
5. Region selector.
6. Additional mobile-layout polish.

---

## 9. Explicitly out of scope

Do not build:

- Satellite imagery.
- Live market feeds.
- Authentication or user accounts.
- SMS or WhatsApp integrations.
- Multi-season rotation.
- Databases.
- Microservices.

---

## 10. Data requirements

Create the following:

### `data/crops.csv`

Include at minimum:

- Crop identifier/name.
- Baseline yield (tonnes/hectare).
- Seasonal water requirement (m³/hectare).
- Cultivation cost (₹/hectare).
- Price (₹/quintal).
- Calories (kcal/kg).
- Drought sensitivity `Ky`.
- Minimum land share.
- Maximum land share.

### `data/weather_scenarios.csv`

Map rainfall scenarios to:

- Effective-rainfall multiplier or equivalent effective rainfall parameter.
- Yield-stress multiplier or equivalent stress parameter.

Include Normal, Deficit, Severe Deficit, and Surplus.

### `data/training_data.csv`

Generated by `scripts/generate_data.py` with a fixed seed.

### `data/ASSUMPTIONS.md`

List every assumed numerical value in one place. State that values are indicative and synthetic demo assumptions.

### `data/loaders/`

Provide documented loader stubs/interfaces showing where real sources can plug in:

- data.gov.in
- ICAR
- IMD
- CGWB
- Agmarknet
- APEDA

Document the expected schema and units. Do not claim these sources have been integrated unless they actually have been.

### Synthetic-data disclosure

Use the exact disclosure:

**“Synthetic demo data calibrated to public agri statistics.”**

Show this in the README and UI footer. Do not imply that synthetic values are official measurements or district-level ground truth.

---

## 11. Backend API contract

Use FastAPI with typed Pydantic v2 request and response models. Expose OpenAPI documentation at `/docs`.

Required endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/config` | Crops, scenarios, limits, defaults |
| GET | `/api/baseline` | Default baseline plan |
| POST | `/api/predict` | ML crop predictions |
| POST | `/api/optimize` | Optimized crop allocation |
| POST | `/api/stress-test` | Extreme scenario and diagnosis |
| POST | `/api/explain` | Optional LLM/template explanation |
| POST | `/api/simulate/sweep` | Water-budget sweep |

Additional requirements:

- Validate input bounds.
- Return structured, understandable errors.
- Do not expose stack traces to clients.
- Enable appropriate CORS for local frontend development.
- Cache identical scenario computations where safe.
- Do not cache stale or incompatible model/solver results.
- Keep numerical computation in predictor/optimizer modules, not API route handlers.

---

## 12. Frontend requirements

Build a responsive single-page application.

### Visual identity

- Earthy-to-aqua palette.
- Deep green, wheat gold, and water blue.
- High contrast.
- Large readable typography.
- Crop icons or clear crop labels.
- Simple farmer-friendly language.
- Mobile-friendly layout.

### Main screen structure

1. Header:
   - AquaShift logo/name.
   - English/Hindi toggle.
   - “Load demo scenario” action.
   - Synthetic-data disclosure badge.
2. Scenario builder:
   - Land, water budget, crop choices, food target, income target, rainfall scenario.
3. Animated six-stage pipeline.
4. Crop plan and KPI cards.
5. Baseline versus optimized allocation charts.
6. Trade-off and water-sweep charts.
7. Stress-test comparison and bottleneck diagnosis.
8. AI insight card.
9. Synthetic-data disclosure in footer.

Handle loading, empty, validation-error, API-error, and successful states.

### Browser verification

- Run the Vite development server.
- Open the actual application in a browser.
- Exercise the scenario builder, optimization, stress test, explanation, and Demo Mode.
- Inspect the browser console.
- Verify at approximately 390px mobile width and desktop width.
- Capture screenshots of the main screens and demo sequence.

Do not mark frontend work verified based only on a successful TypeScript build.

---

## 13. Required repository structure

Use this structure, adding small modules where needed without changing the specified stack:

```text
aquashift/
├── AGENTS/
│   └── rules.md
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── ml/
│   │   ├── optimizer/
│   │   │   ├── model.py
│   │   │   ├── stress.py
│   │   │   ├── diagnosis.py
│   │   │   └── sweep.py
│   │   └── llm/
│   │       ├── explain.py
│   │       ├── validate.py
│   │       └── templates.py
│   └── tests/
├── frontend/
├── data/
│   ├── crops.csv
│   ├── weather_scenarios.csv
│   ├── training_data.csv
│   ├── ASSUMPTIONS.md
│   └── loaders/
├── scripts/
│   ├── generate_data.py
│   ├── train_model.py
│   ├── run_demo.py
│   └── dev.py
└── docs/
    ├── DECISIONS.md
    ├── architecture.md
    ├── demo-script.md
    └── judging-notes.md
```

---

## 14. Required implementation phases and gates

Work sequentially. Finish and verify each phase before starting the next.

### Phase 0 — Scaffold

- Create repository structure.
- Create virtual environment.
- Install pinned dependencies.
- Create minimal FastAPI and Vite shells.
- Confirm pytest and npm development server run.

**Verification:** Backend and frontend start successfully.

### Phase 1 — Data

- Create crop and weather CSV files.
- Implement seeded data generator.
- Create assumptions documentation and loader stubs.

**Verification:** Generate the dataset twice and compare hashes; they must match.

### Phase 2 — ML

- Train and persist the prediction model.
- Implement typed prediction interface and uncertainty ranges.
- Add tests.

**Verification:** Model files exist; predictions are sensible and yield does not rise as water stress worsens, all else equal.

### Phase 3 — Optimization

- Implement baseline.
- Implement GLOP optimizer, hard constraints, soft slacks, weighted and lexicographic modes.
- Implement stress test, diagnosis, and sweep.
- Add tests.

**Verification:**
- Normal scenario returns a valid plan.
- Allocation never exceeds available land.
- Extreme scenario returns a recovery plan if hard constraints permit.
- Water is ranked Critical in the tuned extreme demo.
- Income is High and Food is Moderate.
- Weighted and lexicographic modes exhibit sensible, tested differences.

### Phase 4 — API

- Implement schemas and all required endpoints.
- Add validation, caching, CORS, and structured errors.

**Verification:** Start the server and exercise every endpoint from a terminal script.

### Phase 5 — Explanation

- Implement deterministic templates.
- Implement optional Anthropic integration.
- Implement conservative numeric-claim validation.

**Verification:** No-key explanation works; deliberately fabricated numeric claims are rejected.

### Phase 6 — Frontend

- Build the Tier 1 dashboard.
- Connect real API results.
- Implement pipeline and Demo Mode.
- Verify all flows in browser.

**Verification:** Full browser demo, clean console, desktop and 390px mobile checks, screenshots.

### Phase 7 — Tier 2

- Implement water sweep, priorities, relaxation solves, Hindi, and uncertainty display.

**Verification:** Re-run all backend tests, frontend build, and browser demo.

### Phase 8 — Packaging

- Add optional Tier 3 features only if time permits.
- Complete Docker, README, demo script, judging notes, and CLI demo.

**Verification:** Clean setup, complete tests, frontend build, offline CLI demo, and final browser walkthrough.

---

## 15. Definition of done

The project is complete only when:

- `python scripts/dev.py` or a clearly documented cross-platform equivalent starts backend and frontend together.
- All pytest tests pass.
- Frontend production build completes without TypeScript errors.
- The two-minute Demo Mode works in the browser.
- The CLI demo works offline without an API key.
- Normal scenario produces a valid allocation.
- Extreme scenario shows the strict-solve comparison and closest-feasible recovery.
- Bottleneck ranking matches the tuned demo expectation: Water Critical, Income High, Food Moderate.
- Every user-visible number is traceable to predictor or optimizer output.
- Offline deterministic explanation works.
- README and UI footer clearly disclose synthetic demo data.
- README honestly states model limitations and that AquaShift is not a replacement for agronomic advice.
- Final walkthrough includes screenshots of every main screen and the demo run.

---

## 16. Final deliverables

1. Working AquaShift application.
2. Walkthrough artifact with screenshots of all main screens and the demo run.
3. Two-minute spoken demo script.
4. Five likely judge questions with strong answers:
   - Why not just ask ChatGPT?
   - Where does your data come from?
   - How do you protect farmer income?
   - What if the model is wrong?
   - How would this scale to real districts?
5. Short list of known limitations.
6. Roadmap for calibration and integration with real district data.

---

## 17. Working rules for the coding agent

- Inspect the workspace before editing.
- Preserve useful existing work.
- Execute phases in order.
- Do not silently substitute the stack.
- Do not skip tests.
- Do not claim success without running commands.
- Use fixed random seeds.
- Keep modules small, typed, and documented.
- No secrets in source control.
- No unfinished placeholder TODOs.
- Document ambiguous decisions in `docs/DECISIONS.md` in one concise line.
- If a phase fails verification, fix it before moving on.
- Report commands and actual outputs.
- Distinguish verified work from unverified work.
- Prioritize correctness, robustness, and a reliable live demo over feature count.
