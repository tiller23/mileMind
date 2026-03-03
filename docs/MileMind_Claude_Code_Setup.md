# MileMind: Claude Code Multi-Agent Build Strategy

## TL;DR Architecture

```
milemind/
├── CLAUDE.md                          # Root context (~100 lines, concise)
├── .claude/
│   ├── agents/                        # Subagent definitions
│   │   ├── deterministic-engine.md    # Phase 1 specialist
│   │   ├── tool-wrapper.md            # Phase 2 specialist
│   │   ├── agent-orchestrator.md      # Phase 3 specialist
│   │   ├── eval-harness.md            # Phase 4 specialist
│   │   ├── frontend-dev.md            # Phase 5 specialist
│   │   ├── test-writer.md             # Cross-phase testing agent
│   │   └── code-reviewer.md           # Cross-phase review agent
│   ├── commands/                      # Slash commands
│   │   ├── test-phase.md              # /test-phase - run tests for current phase
│   │   ├── review.md                  # /review - code review workflow
│   │   └── new-feature.md             # /new-feature - branch + plan + implement
│   ├── skills/
│   │   ├── exercise-science/
│   │   │   └── SKILL.md              # Banister, ACWR, Daniels formulas reference
│   │   ├── anthropic-tool-use/
│   │   │   └── SKILL.md              # Claude API tool-use patterns
│   │   └── testing-patterns/
│   │       └── SKILL.md              # Project test conventions
│   └── settings.json                  # Hooks, permissions
├── backend/                           # Python FastAPI
│   ├── CLAUDE.md                      # Backend-specific context
│   ├── src/
│   │   ├── deterministic/             # Phase 1: Pure Python models
│   │   ├── tools/                     # Phase 2: Tool wrappers
│   │   ├── agents/                    # Phase 3: Planner/Reviewer orchestration
│   │   ├── evaluation/                # Phase 4: Harness
│   │   └── api/                       # Phase 5: FastAPI routes
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── e2e/
├── frontend/                          # Next.js + React Native
│   ├── CLAUDE.md                      # Frontend-specific context
│   ├── web/                           # Next.js dashboard
│   └── mobile/                        # React Native (Expo)
└── docs/
    ├── prd.md                         # PRD reference (for agent context)
    └── architecture/                  # ADRs, design docs
```

---

## 1. The Root CLAUDE.md

Keep it under 120 lines. Claude can follow ~150 instructions reliably — the system prompt already consumes ~50. Every line must earn its place.

```markdown
# MileMind

## What
AI-powered running training optimizer. Multi-agent architecture (Planner + Reviewer)
with a deterministic Python domain layer that computes all physiological metrics.
Claude handles planning/review/negotiation; Python handles math. The LLM never
generates physiological numbers directly.

## Stack
- Backend: Python 3.12, FastAPI, PostgreSQL (JSONB), raw Anthropic API
- Frontend: Next.js (web dashboard), React Native/Expo (mobile)
- AI: Claude Sonnet (planner, cost-optimized), Claude Opus (reviewer, safety-critical)
- Testing: pytest (backend), vitest + React Testing Library (frontend)

## Project Structure
- `backend/src/deterministic/` — Pure Python physiological models (NO AI)
- `backend/src/tools/` — JSON-schema tool wrappers for Claude
- `backend/src/agents/` — Planner/Reviewer orchestration with retry loop
- `backend/src/evaluation/` — Synthetic athlete test harness
- `backend/src/api/` — FastAPI routes
- `frontend/web/` — Next.js dashboard
- `frontend/mobile/` — React Native app
- See `docs/prd.md` for full product requirements

## Commands
- `cd backend && pytest` — Run all backend tests
- `cd backend && pytest tests/unit/` — Unit tests only
- `cd backend && pytest tests/unit/deterministic/` — Deterministic engine tests
- `cd backend && pytest tests/integration/` — Integration tests
- `cd frontend/web && npm test` — Frontend tests
- `cd backend && uvicorn src.api.main:app --reload` — Dev server

## Constraints
- MUST: All physiological metrics computed by deterministic Python functions
- MUST: Tool functions have JSON schemas; validate inputs/outputs
- MUST: Every public function has docstring with params, returns, raises
- MUST: Tests before committing. No PR without passing tests
- MUST NOT: LLM generating TSS, CTL, ATL, TSB, ACWR, VO2max, or pace values
- MUST NOT: `any` types in TypeScript frontend code
- NEVER: Modify migration files directly
- NEVER: Commit API keys or secrets

## Testing Rules
- Unit tests: 100% coverage on deterministic models (Phase 1 gate)
- Unit tests: Every tool wrapper validates schema compliance
- Integration tests: Agent loop produces valid plans for all 5 synthetic personas
- E2E: Full plan generation → negotiation → adaptation cycle
- Test files mirror source: `src/deterministic/banister.py` → `tests/unit/deterministic/test_banister.py`

## Git Workflow
- Branch per feature: `feature/phase-{N}-{description}`
- Commit messages: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`
- Merge to main only after all phase gates pass

## When Compacting
Always preserve: list of modified files, current phase, test results, and any failing test details.
```

### Backend-specific CLAUDE.md (`backend/CLAUDE.md`)

```markdown
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
```

---

## 2. Subagent Definitions

Subagents are the key multiplier. Each runs in its own context window, so they don't pollute your main conversation. Define them as markdown files with YAML frontmatter in `.claude/agents/`.

### Core Principle: Phase-Specific + Cross-Cutting

**Phase-specific agents** know the domain deeply for one phase.
**Cross-cutting agents** (testing, review) operate across all phases.

### Agent: Deterministic Engine Builder (Phase 1)

`.claude/agents/deterministic-engine.md`:
```markdown
---
name: deterministic-engine
description: >
  Builds and tests the pure Python deterministic physiological models.
  Use for: Banister fitness-fatigue model, VO2max/VDOT calculations,
  ACWR injury risk, taper decay, Monte Carlo race simulation.
  All exercise science math with zero AI involvement.
tools: Read, Write, Edit, Bash, Glob, Grep
model: opus
---

You are an exercise science computation specialist building MileMind's
deterministic domain layer in pure Python.

## Your Domain
- Banister impulse-response model (CTL, ATL, TSB with configurable τ)
- Daniels-Gilbert VO2 expenditure equations and VDOT pace tables
- Karvonen heart rate zone calculations
- ACWR with rolling average AND EWMA variants
- Taper decay via impulse-response with zero future training load
- Monte Carlo race simulation with pace distributions

## Critical Rules
- ALL functions must be pure Python. No LLM calls. No network calls.
- Every function must have type hints, docstring, and edge case handling.
- Reference implementations: see `.claude/skills/exercise-science/SKILL.md`
- Use numpy/scipy only where genuinely needed (prefer stdlib math)
- Every model MUST have unit tests with known outputs from published
  exercise science literature

## Output Structure
All models go in `backend/src/deterministic/`
All tests go in `backend/tests/unit/deterministic/`

## Verification
After writing any model, immediately run:
`cd backend && pytest tests/unit/deterministic/ -v`
Do not consider work complete until all tests pass.
```

### Agent: Tool Wrapper Builder (Phase 2)

`.claude/agents/tool-wrapper.md`:
```markdown
---
name: tool-wrapper
description: >
  Wraps deterministic models as Claude-callable tools with JSON schemas.
  Use for: compute_training_stress, evaluate_fatigue_state,
  validate_progression_constraints, simulate_race_outcomes, reallocate_week_load.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
---

You are a tool-layer specialist wrapping MileMind's deterministic models
as callable tools for Claude's tool-use API.

## Your Responsibilities
- Define JSON schemas (input/output) for each deterministic function
- Build the execution layer that validates inputs against schemas
- Ensure the LLM can ONLY get physiological metrics through these tools
- Write comprehensive validation tests

## Tool Inventory
| Tool | Wraps | Input | Output |
|------|-------|-------|--------|
| compute_training_stress | banister.py | workout type, duration, intensity | TSS/TRIMP, load class |
| evaluate_fatigue_state | banister.py | athlete_id, date_range | CTL, ATL, TSB, status |
| validate_progression_constraints | acwr.py | proposed weekly plan | pass/fail + violations |
| simulate_race_outcomes | monte_carlo.py | athlete state, race params | finish time distribution |
| reallocate_week_load | All models | plan, constraints, swap request | adjusted plan |

## Schema Pattern
```python
TOOL_SCHEMA = {
    "name": "compute_training_stress",
    "description": "...",
    "input_schema": {
        "type": "object",
        "properties": {...},
        "required": [...]
    }
}
```

## Verification
After writing each tool wrapper:
`cd backend && pytest tests/unit/tools/ -v`
```

### Agent: Agent Orchestrator Builder (Phase 3)

`.claude/agents/agent-orchestrator.md`:
```markdown
---
name: agent-orchestrator
description: >
  Builds the Planner-Reviewer multi-agent orchestration loop.
  Use for: Claude API integration, system prompts, retry logic,
  convergence tracking, decision logging.
tools: Read, Write, Edit, Bash, Glob, Grep
model: opus
---

You build MileMind's multi-agent orchestration: the Planner and Reviewer
agents communicating via the raw Anthropic API with tool-use.

## Architecture
- Planner Agent (Claude Sonnet): proposes plans using tool calls
- Reviewer Agent (Claude Opus): evaluates safety independently
- Orchestrator: manages the retry loop between them
- Max retries: 5 (configurable). Fallback: last safest plan + warnings

## Critical Design Rules
- Raw `anthropic` Python SDK. No LangChain, no frameworks.
- Planner's system prompt MUST enforce tool-only metric generation
- Reviewer has NO knowledge of Planner's reasoning
- Every interaction logged to `agent_decision_log` table
- Track: retry count, failure reasons, convergence time, token usage

## Planner System Prompt Must Include
- Available tools with schemas
- Constraint: "You MUST use tools for all physiological calculations"
- Constraint: "Any response containing un-sourced numbers will be rejected"

## Verification
`cd backend && pytest tests/integration/agents/ -v`
Test that the loop converges for all 5 synthetic personas.
```

### Agent: Test Writer (Cross-Phase)

`.claude/agents/test-writer.md`:
```markdown
---
name: test-writer
description: >
  Writes comprehensive tests for any MileMind component. Use for:
  unit tests, integration tests, e2e tests, synthetic athlete tests,
  schema validation tests, convergence tests.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
---

You are MileMind's dedicated test engineer.

## Testing Strategy by Layer

### Unit Tests (backend/tests/unit/)
- Deterministic models: parametrized tests with known exercise science outputs
- Tool wrappers: schema validation, input rejection, output format
- Pydantic models: serialization/deserialization round-trips

### Integration Tests (backend/tests/integration/)
- Agent loop: converges within 3 retries for standard personas
- Tool execution: end-to-end tool call → deterministic calculation → response
- Feedback loop: deviation detection triggers replan

### E2E Tests (backend/tests/e2e/)
- Full plan generation pipeline for each synthetic persona
- Chat negotiation → replan → validation cycle
- API endpoint contracts (request/response shapes)

## Synthetic Test Personas
1. Beginner Runner (5-8 mpw, no history) → conservative walk-run
2. Overtrained Athlete (high load, negative TSB) → immediate load reduction
3. Aggressive Spiker (requests 40% increase) → system rejects
4. Injury-Prone Runner (IT-band history) → low-impact alternatives
5. Advanced Marathoner (60+ mpw) → sophisticated periodization

## Test Conventions
- Use pytest fixtures for athlete profiles and shared state
- Use `pytest.mark.parametrize` for multi-persona sweeps
- Use `pytest.approx()` for floating-point comparisons
- Every test has a descriptive docstring explaining WHAT and WHY
- Mirror source structure: `src/x/y.py` → `tests/unit/x/test_y.py`

## After Writing Tests
Always run them: `cd backend && pytest {test_path} -v`
```

### Agent: Code Reviewer (Cross-Phase)

`.claude/agents/code-reviewer.md`:
```markdown
---
name: code-reviewer
description: >
  Reviews MileMind code for safety, correctness, and architecture.
  Use after implementing features or before merging.
tools: Read, Glob, Grep, Bash
model: opus
---

You review MileMind code with focus on:

## Safety Checklist
- [ ] No physiological metrics generated outside deterministic layer
- [ ] All tool outputs validated against JSON schemas
- [ ] ACWR hard-capped at 1.5 regardless of athlete preferences
- [ ] No raw user input passed to LLM without sanitization

## Code Quality Checklist
- [ ] Type hints on all functions
- [ ] Docstrings with params, returns, raises
- [ ] Error handling with meaningful context
- [ ] No nested depth > 4 levels
- [ ] Functions under 50 lines
- [ ] Tests exist and pass

## Architecture Checklist
- [ ] Clear layer boundaries (deterministic ↔ tool ↔ agent ↔ API)
- [ ] No circular imports
- [ ] Pydantic models for all data boundaries
- [ ] Decision logging present for agent interactions

Report findings as: CRITICAL / WARNING / SUGGESTION with file:line references.
```

---

## 3. Skills (Progressive Disclosure)

Skills inject domain knowledge only when relevant, keeping your context clean.

### Exercise Science Skill

`.claude/skills/exercise-science/SKILL.md`:
```markdown
---
name: exercise-science
description: >
  Reference formulas and expected values for MileMind's deterministic
  physiological models. Banister, Daniels, ACWR, taper decay.
---

# Exercise Science Reference

## Banister Impulse-Response Model
- Fitness (CTL): exponential moving average, τ1 = 42 days (default)
- Fatigue (ATL): exponential moving average, τ2 = 7 days (default)
- Form (TSB): CTL - ATL
- Formula: w(t) = w(0) * e^(-t/τ)

## Daniels-Gilbert VO2 Equations
- VO2 = -4.60 + 0.182258 * v + 0.000104 * v^2  (v in m/min)
- %VO2max = 0.8 + 0.1894393 * e^(-0.012778 * t) + 0.2989558 * e^(-0.1932605 * t)
- Reference: github.com/mekeetsa/vdot

## ACWR Thresholds
- Safe zone: 0.8 - 1.3
- Warning zone: 1.3 - 1.5
- Hard cap: 1.5 (system rejects regardless of preference)
- Calculate with both rolling 7:28 day ratio AND EWMA

## Known Test Values
- 5K in 20:00 → VDOT ≈ 46.8
- Marathon in 3:30:00 → VDOT ≈ 46.2
- CTL after 30 days of 50 TSS/day (τ=42): ~25.6

## Reference Repos
- Banister: GoldenCheetah (C++), choochoo (Python)
- VDOT: mekeetsa/vdot, st3v/running-formulas-mcp
- ACWR: ale-uy/Acute_Chronic_Workload_Ratio (Python)
- Monte Carlo: mountain-software-jp/trail-simulator (Python)
```

---

## 4. Hooks (Automated Guardrails)

`.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "[ \"$(git branch --show-current)\" != \"main\" ] || { echo '{\"block\": true, \"message\": \"Cannot edit on main branch. Create a feature branch first.\"}' >&2; exit 2; }",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash(pytest*)",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Tests completed. Check results above.'",
            "timeout": 5
          }
        ]
      }
    ]
  },
  "permissions": {
    "allow": [
      "Bash(cd backend && pytest*)",
      "Bash(cd frontend/* && npm test*)",
      "Bash(cd backend && ruff*)",
      "Bash(cd backend && black*)",
      "Bash(cd frontend/* && npm run lint*)",
      "Bash(git *)",
      "Bash(pip install*)",
      "Bash(npm install*)",
      "Read",
      "Glob",
      "Grep"
    ]
  }
}
```

---

## 5. Slash Commands

### `/test-phase` — Run Phase-Specific Tests

`.claude/commands/test-phase.md`:
```markdown
---
description: Run tests for a specific MileMind phase
allowed-tools: Read, Bash, Glob
---

Run the test suite for phase: $ARGUMENTS

Phase mapping:
- 1: `cd backend && pytest tests/unit/deterministic/ -v --tb=short`
- 2: `cd backend && pytest tests/unit/tools/ -v --tb=short`
- 3: `cd backend && pytest tests/integration/agents/ -v --tb=short`
- 4: `cd backend && pytest tests/e2e/ -v --tb=short`
- 5: `cd frontend/web && npm test -- --run`
- all: `cd backend && pytest -v --tb=short && cd ../frontend/web && npm test -- --run`

Run the appropriate command, then report: total, passed, failed, coverage gaps.
```

### `/new-feature` — Branched Feature Workflow

`.claude/commands/new-feature.md`:
```markdown
---
description: Start a new feature with branch, plan, implement, test
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

Feature: $ARGUMENTS

1. Create branch: `git checkout -b feature/$ARGUMENTS`
2. Enter plan mode: outline the approach, files to modify, tests needed
3. Wait for approval before implementing
4. Implement with tests
5. Run full test suite for the relevant phase
6. Commit with descriptive message
```

---

## 6. Testing Strategy

### The Testing Pyramid for MileMind

```
         ┌──────────┐
         │   E2E    │  5-10 tests: Full pipeline, API contracts
         │          │  Slow, expensive (uses Claude API)
        ┌┴──────────┴┐
        │ Integration │  20-30 tests: Agent loop, tool execution,
        │             │  feedback triggers. Mock Claude API responses.
       ┌┴─────────────┴┐
       │   Unit Tests   │  100+ tests: Every deterministic function,
       │                │  every schema, every edge case.
       └────────────────┘  Fast, no external deps. 100% coverage on Phase 1.
```

### Unit Tests: The Foundation (Phase 1 Gate)

```python
# tests/unit/deterministic/test_banister.py

import pytest
from src.deterministic.banister import compute_ctl, compute_atl, compute_tsb

class TestBanisterModel:
    """Tests against known exercise science literature values."""

    @pytest.fixture
    def steady_state_load(self):
        """30 days of constant 50 TSS/day training."""
        return [50.0] * 30

    def test_ctl_steady_state(self, steady_state_load):
        """CTL after 30 days at 50 TSS/day with τ=42 should be ~25.6."""
        ctl = compute_ctl(steady_state_load, tau=42)
        assert ctl == pytest.approx(25.6, abs=0.5)

    def test_atl_steady_state(self, steady_state_load):
        """ATL after 30 days at 50 TSS/day with τ=7 should be ~49.2."""
        atl = compute_atl(steady_state_load, tau=7)
        assert atl == pytest.approx(49.2, abs=0.5)

    def test_tsb_is_ctl_minus_atl(self, steady_state_load):
        """TSB = CTL - ATL by definition."""
        ctl = compute_ctl(steady_state_load, tau=42)
        atl = compute_atl(steady_state_load, tau=7)
        tsb = compute_tsb(steady_state_load)
        assert tsb == pytest.approx(ctl - atl, abs=0.01)

    @pytest.mark.parametrize("tau,expected_range", [
        (42, (20, 30)),    # Standard fitness decay
        (7, (45, 52)),     # Standard fatigue decay
        (100, (10, 18)),   # Very slow adaptation
    ])
    def test_ctl_varies_with_tau(self, steady_state_load, tau, expected_range):
        """Different time constants produce different adaptation rates."""
        ctl = compute_ctl(steady_state_load, tau=tau)
        assert expected_range[0] <= ctl <= expected_range[1]

    def test_zero_load_decays_to_zero(self):
        """With no training, fitness should decay toward zero."""
        load = [100.0] * 10 + [0.0] * 100
        ctl = compute_ctl(load, tau=42)
        assert ctl < 5.0  # Should be near zero after 100 rest days

    def test_empty_history_raises(self):
        """Empty training history should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            compute_ctl([], tau=42)
```

```python
# tests/unit/deterministic/test_acwr.py

import pytest
from src.deterministic.acwr import compute_acwr, check_safety

class TestACWR:
    """ACWR calculation and safety boundary tests."""

    def test_safe_zone(self):
        """Steady training should produce ACWR in safe zone (0.8-1.3)."""
        weekly_loads = [100, 100, 100, 100, 105]  # 4-week chronic + 1 acute
        acwr = compute_acwr(weekly_loads)
        assert 0.8 <= acwr <= 1.3

    def test_spike_detection(self):
        """Sudden 40% increase should flag as dangerous."""
        weekly_loads = [100, 100, 100, 100, 140]
        result = check_safety(weekly_loads)
        assert result.safe is False
        assert "spike" in result.violations[0].lower()

    def test_hard_cap_at_1_5(self):
        """ACWR above 1.5 MUST be rejected regardless of preference."""
        weekly_loads = [50, 50, 50, 50, 100]  # 2x spike
        result = check_safety(weekly_loads, risk_tolerance="aggressive")
        assert result.safe is False  # Even aggressive can't bypass 1.5
```

### Integration Tests: Agent Loop (Phase 3 Gate)

```python
# tests/integration/agents/test_agent_loop.py

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.orchestrator import PlannerReviewerLoop
from src.evaluation.personas import SYNTHETIC_PERSONAS

class TestAgentLoop:
    """Test that the Planner-Reviewer loop converges safely."""

    @pytest.fixture
    def orchestrator(self):
        return PlannerReviewerLoop(max_retries=5)

    @pytest.mark.parametrize("persona", SYNTHETIC_PERSONAS.keys())
    @pytest.mark.asyncio
    async def test_converges_for_all_personas(self, orchestrator, persona):
        """Every synthetic persona should get a safe plan within 5 retries."""
        profile = SYNTHETIC_PERSONAS[persona]
        result = await orchestrator.generate_plan(profile)

        assert result.converged is True
        assert result.retry_count <= 5
        assert result.safety_score >= 85

    @pytest.mark.asyncio
    async def test_aggressive_spiker_rejected(self, orchestrator):
        """A 40% mileage increase request MUST be rejected and reduced."""
        profile = SYNTHETIC_PERSONAS["aggressive_spiker"]
        result = await orchestrator.generate_plan(profile)

        # Plan should exist but with reduced progression
        assert result.converged is True
        max_weekly_increase = max(
            result.plan.week_over_week_increases()
        )
        assert max_weekly_increase <= 0.20  # Capped at 20% max

    @pytest.mark.asyncio
    async def test_decision_log_populated(self, orchestrator):
        """Every agent interaction must be logged."""
        profile = SYNTHETIC_PERSONAS["beginner_runner"]
        result = await orchestrator.generate_plan(profile)

        assert len(result.decision_log) > 0
        for entry in result.decision_log:
            assert entry.agent_role in ("planner", "reviewer")
            assert entry.tool_calls is not None
            assert entry.token_usage > 0
```

### E2E Tests: Full Pipeline (Phase 4-5 Gate)

```python
# tests/e2e/test_full_pipeline.py

import pytest
from httpx import AsyncClient
from src.api.main import app

class TestFullPipeline:
    """End-to-end tests against the running API."""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_plan_generation_endpoint(self, client):
        """POST /api/v1/plans/generate returns a valid plan."""
        response = await client.post("/api/v1/plans/generate", json={
            "athlete_id": "test-beginner",
            "goal_event": "5K",
            "goal_date": "2026-06-01",
            "current_weekly_miles": 8,
        })
        assert response.status_code == 200
        plan = response.json()
        assert "weeks" in plan
        assert len(plan["weeks"]) > 0
        assert plan["safety_score"] >= 85

    @pytest.mark.asyncio
    async def test_negotiate_endpoint(self, client):
        """POST /api/v1/plans/{id}/negotiate modifies plan safely."""
        # First generate a plan
        gen = await client.post("/api/v1/plans/generate", json={...})
        plan_id = gen.json()["id"]

        # Then negotiate
        response = await client.post(
            f"/api/v1/plans/{plan_id}/negotiate",
            json={"message": "Move my long run to Saturday"}
        )
        assert response.status_code == 200
        assert response.json()["modified"] is True

    @pytest.mark.asyncio
    async def test_debug_trace_endpoint(self, client):
        """GET /api/v1/plans/{id}/debug_trace returns full agent history."""
        gen = await client.post("/api/v1/plans/generate", json={...})
        plan_id = gen.json()["id"]

        response = await client.get(f"/api/v1/plans/{plan_id}/debug_trace")
        assert response.status_code == 200
        trace = response.json()
        assert "iterations" in trace
        assert trace["iterations"][0]["agent_role"] == "planner"
```

### Frontend Tests

```typescript
// frontend/web/__tests__/components/TrainingLoadChart.test.tsx

import { render, screen } from '@testing-library/react';
import { TrainingLoadChart } from '@/components/TrainingLoadChart';

describe('TrainingLoadChart', () => {
  const mockData = {
    dates: ['2026-01-01', '2026-01-02', '2026-01-03'],
    ctl: [30, 31, 32],
    atl: [45, 43, 41],
    tsb: [-15, -12, -9],
  };

  it('renders CTL, ATL, and TSB lines', () => {
    render(<TrainingLoadChart data={mockData} />);
    expect(screen.getByText('Fitness (CTL)')).toBeInTheDocument();
    expect(screen.getByText('Fatigue (ATL)')).toBeInTheDocument();
    expect(screen.getByText('Form (TSB)')).toBeInTheDocument();
  });

  it('shows projected values as shaded area', () => {
    render(<TrainingLoadChart data={mockData} showProjection />);
    expect(screen.getByTestId('projection-area')).toBeInTheDocument();
  });
});
```

---

## 7. Phase Execution Workflow

### How to Actually Run Each Phase

**General pattern for every phase:**

```
1. Start Claude Code in the project root
2. /new-feature phase-{N}-{component}
3. Use plan mode first: "Plan the implementation for {component}"
4. Approve the plan
5. "Use the {relevant-agent} subagent to implement this"
6. "Use the test-writer subagent to write tests for {component}"
7. /test-phase {N}
8. "Use the code-reviewer subagent to review changes"
9. Fix issues, re-test
10. git commit + merge when green
```

### Phase 1 Example Session

```
you: I'm starting Phase 1. First, let's build the Banister fitness-fatigue
     model. Use the deterministic-engine subagent to implement the
     impulse-response model with configurable time constants.

[Claude delegates to deterministic-engine subagent]
[Subagent reads .claude/skills/exercise-science/SKILL.md for formulas]
[Subagent writes backend/src/deterministic/banister.py]
[Subagent runs tests automatically]

you: Now use the test-writer subagent to add edge case tests —
     empty history, negative values, extreme time constants.

[test-writer subagent adds parametrized tests]
[runs pytest, reports results]

you: /test-phase 1

[runs full Phase 1 test suite]
```

### Parallel Work with Git Worktrees (Phase 5)

When you hit Phase 5, you can run multiple Claude Code instances in parallel:

```bash
# Create worktrees for parallel frontend/backend work
git worktree add ../milemind-frontend feature/phase-5-frontend
git worktree add ../milemind-api feature/phase-5-api-routes

# Terminal 1: Frontend work
cd ../milemind-frontend && claude

# Terminal 2: API routes
cd ../milemind-api && claude
```

Each instance has its own conversation context and branch. Merge when both are green.

---

## 8. Cost Optimization Tips

1. **Subagent model routing**: Phase 1-2 work is deterministic Python — use `model: sonnet`
   in those agents. Reserve `model: opus` for Phase 3 (agent orchestration) and code review.

2. **Mock Claude API in integration tests**: Don't burn real API tokens on every test run.
   Record real responses once, replay them. Only run live integration tests before merge.

3. **Context management**: Use `/clear` aggressively between phases. Subagents are your
   best friend for keeping the main context clean.

4. **Compaction instructions**: The CLAUDE.md `When Compacting` section ensures you don't
   lose critical state when context fills up.

---

## 9. Quick Start Checklist

```
[ ] Initialize repo: git init milemind
[ ] Create directory structure (see top of this doc)
[ ] Write root CLAUDE.md
[ ] Write backend/CLAUDE.md
[ ] Create all .claude/agents/*.md files
[ ] Create .claude/skills/exercise-science/SKILL.md
[ ] Create .claude/settings.json with hooks
[ ] Create .claude/commands/ slash commands
[ ] pip install fastapi uvicorn pydantic pytest pytest-asyncio httpx numpy
[ ] npm init in frontend/web (Next.js) and frontend/mobile (Expo)
[ ] Copy PRD to docs/prd.md for agent reference
[ ] First commit on main
[ ] Start Phase 1: git checkout -b feature/phase-1-banister
[ ] Launch Claude Code: claude
```
