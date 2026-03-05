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

## API Cost Safeguards

All Claude API calls are gated by multiple limits to prevent runaway costs:

| Safeguard | Default | Where |
|-----------|---------|-------|
| CLI confirmation prompt | enabled (skip with `-y`) | `cli.py` |
| Planner max_iterations | 15 | `PlannerAgent.__init__` |
| Reviewer max_iterations | 10 | `ReviewerAgent.__init__` |
| Orchestrator max_retries | 3 | `Orchestrator.__init__` |
| **Token budget** | **1,000,000** | `Orchestrator.__init__` |
| Planner max_tokens/call | 8,192 | `_run_agent_loop` |
| Reviewer max_tokens/call | 4,096 | `_run_agent_loop` |

**Pricing reference** (Sonnet planner, Opus reviewer):
- Happy path (1 cycle, ~7+3 iterations): **~$0.52**
- Typical run (1-2 cycles): **~$0.52-$1.04**
- Token budget worst case (1M tokens): **~$7.50**
- Uncapped theoretical max (3×15 + 3×10 iters): ~$13 — prevented by token budget

The `max_total_tokens` budget is the hard backstop. Override via
`Orchestrator(max_total_tokens=N)` or accept the 1M default.

## Cost Optimization Patterns

See `docs/cost-optimization.md` for the full cost optimization roadmap.

**Built-in patterns (implemented):**
- `PlanChangeType` enum: `FULL` (default), `ADAPTATION` (1 retry), `TWEAK` (no reviewer)
- `MessageTransport` Protocol: swappable API transport (enables batch, mocks)
- `AthleteProfile.cache_key()`: SHA-256 hash for response deduplication
- CLI: `--change-type full|adaptation|tweak` routes through orchestrator

## Test Commands
- `pytest tests/unit/deterministic/ -v` — Deterministic model tests
- `pytest tests/unit/tools/ -v` — Tool schema validation tests
- `pytest tests/integration/agents/ -v` — Agent loop convergence tests
- `pytest tests/e2e/ -v` — Full pipeline tests
- `pytest --cov=src --cov-report=term-missing` — Coverage report
