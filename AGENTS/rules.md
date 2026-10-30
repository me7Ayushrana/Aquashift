# AquaShift — Agent Rules and Engineering Standards

## 1. Core Principles

1. **ML Predicts**: Yield and water demand are estimated by calibrated machine learning models.
2. **Optimization Decides**: Crop allocation decisions are made solely by mathematical programming (Google OR-Tools GLOP linear solver).
3. **AI Explains**: Claude / LLM translates numerical plan outputs into plain language for farmers and planners. The LLM **never** calculates, optimizes, modifies, or hallucinates numbers.
4. **No Bare Infeasible**: Extreme or over-constrained scenarios must execute a recovery solve using soft constraints and slack variables, diagnosing bottlenecks rather than returning an unhelpful `INFEASIBLE` error.
5. **Full Offline Capability**: The application must function deterministically without an Anthropic API key, using structured template fallbacks.
6. **Synthetic Data Disclosure**: Any demo/synthetic data must carry the mandatory label:
   > *"Synthetic demo data calibrated to public agri statistics."*

## 2. Technical Stack Constraints

- **Backend**: Python 3.11, FastAPI, Pydantic v2, Uvicorn, OR-Tools GLOP (`pywraplp`), scikit-learn, joblib, pandas, pytest.
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Recharts, Lucide React.
- **No Database**: Flat files (CSV and JSON) only. No ORM, no SQL, no SQLite.
- **No Microservices**: Monolithic API backend and single-page application.
- **Cross-Platform**: All scripts must be executable across macOS, Linux, and Windows via Python and npm without bash-only dependencies.

## 3. Engineering & Verification Discipline

- Work sequentially across development phases (Phase 0 through Phase 8).
- Do not mark any gate complete without running terminal commands and inspecting outputs.
- Preserve existing reference files (`PROJECT_SPEC.md`, `AquaShift_Implementation_Plan.md`, `AquaShift.pptx`).
- Document all non-obvious engineering decisions in `docs/DECISIONS.md`.
- Keep modules typed, documented, and small with single responsibilities.
- Validate all user-facing numerical values against the optimizer JSON output.
