# MileMind Backend

## Python Conventions
- Python 3.12, type hints on all functions
- Use pydantic for all data models and validation
- Use pytest with fixtures, parametrize for edge cases
- Async FastAPI routes, sync deterministic functions
- `ruff` for linting, `black` for formatting

## Deterministic Engine Reference
For exercise science formulas and expected behaviors, see:
`.claude/skills/exercise-science/SKILL.md`

## Key Models
- `backend/src/deterministic/banister.py` — Fitness-Fatigue (CTL/ATL/TSB)
- `backend/src/deterministic/daniels.py` — VO2max, VDOT, pace zones
- `backend/src/deterministic/acwr.py` — Acute-to-Chronic Workload Ratio
- `backend/src/deterministic/taper.py` — Taper decay modeling
- `backend/src/deterministic/monte_carlo.py` — Race simulation

## Test Commands
- `pytest tests/unit/deterministic/ -v` — Deterministic model tests
- `pytest tests/unit/tools/ -v` — Tool schema validation tests
- `pytest tests/integration/agents/ -v` — Agent loop convergence tests
- `pytest tests/e2e/ -v` — Full pipeline tests
- `pytest --cov=src --cov-report=term-missing` — Coverage report
