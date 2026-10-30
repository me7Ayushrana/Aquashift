# AquaShift — Implementation Plan & Task List

**Hackathon:** Zinnovatio 4.0, AgriTech & Rural Transformation  
**Team:** NullPointers  
**Product:** Water-constrained crop planning and diversification simulator  
**Tagline:** Plan crops. Balance water. Protect livelihoods.

## Product contract

- ML predicts crop yield and water demand.
- OR-Tools makes every allocation decision.
- The optional LLM explains solver output; it never computes or changes numbers.
- The complete application works offline without an Anthropic API key.
- Extreme scenarios return the closest feasible plan with slack and bottleneck diagnosis.
- Synthetic demo data is disclosed in the README and UI footer.
- No database, authentication, microservices, live market feeds, or satellite imagery.

## Architecture

- Backend: Python 3.11, FastAPI, Pydantic v2, Uvicorn, OR-Tools GLOP, scikit-learn, joblib, pandas, pytest.
- Frontend: React, Vite, TypeScript, Tailwind CSS, Recharts.
- Optional explanation: Anthropic Python SDK; `ANTHROPIC_MODEL` and optional `ANTHROPIC_API_KEY`.
- Persistence: versioned CSV/JSON files.
- Reproducibility: fixed seeds and pinned dependencies.

## Phased execution checklist

### Phase 0 — Scaffold
- [ ] Inspect existing workspace and preserve useful files.
- [ ] Create repository structure and project rules.
- [ ] Create pinned backend and frontend dependencies.
- [ ] Add `.env.example`, `.gitignore`, and cross-platform scripts.
- [ ] Create minimal FastAPI and Vite shells.
- [ ] Verify backend tests and frontend dev server start.

**Gate:** Both shells start successfully; dependency versions are pinned.

### Phase 1 — Data
- [ ] Create `data/crops.csv` for Paddy, Wheat, Maize, Pulses, Millets.
- [ ] Create `data/weather_scenarios.csv`.
- [ ] Implement seeded `scripts/generate_data.py`.
- [ ] Create `data/training_data.csv`.
- [ ] Write `data/ASSUMPTIONS.md` with every indicative numeric assumption.
- [ ] Add real-data loader interface documentation for data.gov.in, ICAR, IMD, CGWB, Agmarknet, APEDA.
- [ ] Verify two generated datasets have identical hashes.

**Gate:** Reproducible data generation and clear synthetic-data labeling.

### Phase 2 — ML
- [ ] Generate agronomically structured synthetic training examples.
- [ ] Implement yield and water-demand prediction per crop and scenario.
- [ ] Use seeded scikit-learn models and persist with joblib.
- [ ] Return uncertainty intervals.
- [ ] Add predictor tests, including monotonic yield response under worsening water stress.

**Gate:** Model artifacts exist; tests pass; predictions behave monotonically.

### Phase 3 — Optimization
- [ ] Implement baseline paddy-heavy allocation.
- [ ] Implement GLOP continuous-hectare decision model.
- [ ] Enforce hard total-land and crop min/max-share constraints.
- [ ] Model water, food and income targets with non-negative slack.
- [ ] Implement normalized weighted-slack objective and water-use tie-breaker.
- [ ] Implement sequential lexicographic water → food → income solves.
- [ ] Return allocation, deltas, totals, gaps, slack, binding constraints, shadow prices and solve time.
- [ ] Implement strict-solve comparison and closest-feasible recovery.
- [ ] Implement bottleneck ranking and water sweep.
- [ ] Tune and document the demo extreme case: Water Critical, Income High, Food Moderate.
- [ ] Test normal feasibility, land bound, extreme recovery and objective modes.

**Gate:** No user-facing bare `INFEASIBLE`; all solver outputs are tested and traceable.

### Phase 4 — API
- [ ] Add typed Pydantic request/response schemas.
- [ ] Implement `/api/health`, `/api/config`, `/api/baseline`.
- [ ] Implement `/api/predict`, `/api/optimize`, `/api/stress-test`.
- [ ] Implement `/api/explain`, `/api/simulate/sweep`.
- [ ] Add bounds validation, clean error responses, CORS and identical-scenario caching.
- [ ] Run the server and exercise every endpoint from a terminal script.

**Gate:** All endpoints return validated contracts; no stack traces leak to clients.

### Phase 5 — Explanation
- [ ] Build deterministic farmer and planner explanation templates.
- [ ] Add optional Claude integration using environment configuration.
- [ ] Validate generated numeric claims against solver JSON.
- [ ] Reject fabricated or unsupported numbers and use deterministic fallback.
- [ ] Keep explanation lazy so optimization results render first.
- [ ] Test no-key operation and deliberately fabricated-number rejection.

**Gate:** Offline explanation works; unsupported numeric claims never reach the user.

### Phase 6 — Frontend and demo
- [ ] Build responsive single-page dashboard with earthy-to-aqua palette.
- [ ] Add scenario inputs and crop selection.
- [ ] Add animated six-step pipeline.
- [ ] Add baseline vs optimized allocation visualization.
- [ ] Add Water, Food and Income KPI cards.
- [ ] Add stress-test comparison and bottleneck diagnosis.
- [ ] Add AI insight card with numeric-verification badge.
- [ ] Add loading, empty and error states.
- [ ] Implement one-click two-minute Demo Mode with captions.
- [ ] Verify full flow in browser, inspect console, capture screenshots.
- [ ] Test desktop and 390px mobile viewport.

**Gate:** The complete demo runs in browser without console errors.

### Phase 7 — Tier 2
- [ ] Water sweep chart and tipping point.
- [ ] Water/Food/Income priority sliders.
- [ ] Water-first toggle.
- [ ] Solver-computed relaxation suggestions.
- [ ] English/Hindi UI and explanation toggle.
- [ ] Prediction uncertainty display.
- [ ] Re-run all backend and frontend checks.

**Gate:** Tier 1 remains stable after enhancements.

### Phase 8 — Final packaging
- [ ] Add CSV and one-page PDF export only if time permits.
- [ ] Add Docker configuration.
- [ ] Write README with architecture diagram, setup, limitations and roadmap.
- [ ] Write `docs/demo-script.md` and `docs/judging-notes.md`.
- [ ] Implement `scripts/run_demo.py` as offline CLI backup.
- [ ] Create walkthrough with screenshots of all main screens and demo steps.
- [ ] Run final clean-install, tests, build and browser walkthrough.

**Gate:** Reproducible offline demo, passing tests, documented limitations and final evidence.

## Acceptance criteria

- `python scripts/dev.py` (or documented equivalent) starts backend and frontend.
- All pytest tests pass.
- Frontend production build has no TypeScript errors.
- Normal scenario solves and allocation never exceeds land.
- Extreme scenario returns a closest-feasible plan with Water Critical, Income High, Food Moderate.
- Claude key is optional; offline fallback is complete.
- All displayed numerical values are sourced from ML or solver outputs.
- Synthetic data is labeled in README and visible UI footer.
- Browser demo and CLI demo both work without an API key.

## Demo narrative (2 minutes)

1. Show the paddy-heavy baseline.
2. Reduce water availability by 20%.
3. Run optimization and explain crop allocation changes.
4. Compare water use, food production and farmer income against baseline and targets.
5. Trigger the extreme scenario: water −80%, income target +50%, food target +10%.
6. Contrast strict solver infeasibility with AquaShift's closest-feasible plan.
7. Show Water Critical, Income High and Food Moderate diagnosis.
8. Load the verified AI explanation and close with: “Plan crops. Balance water. Protect livelihoods.”

## Risks and safeguards

- Synthetic assumptions are indicative, not field recommendations.
- LP shadow prices are local model sensitivities, not guaranteed market values.
- Strict infeasibility and soft-constraint recovery must be clearly distinguished.
- A numeric validator must be conservative; uncertain LLM output falls back to templates.
- Do not claim real-world agronomic validity without calibration against local data.
- Never sacrifice solver correctness or offline reliability for extra UI features.

## Workspace execution note

Use the user's Antigravity workspace as the source of truth. Inspect existing files before scaffolding, execute one phase at a time, run its verification gate, and record decisions in `docs/DECISIONS.md`. Do not mark a phase complete based on code inspection alone.
