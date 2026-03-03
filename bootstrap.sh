#!/usr/bin/env bash
# bootstrap.sh - Minimal Claude Code setup for MileMind
# Creates: directory skeleton + CLAUDE.md files (from setup guide)
# You handle: agents, skills, commands, settings (via Claude Code)
set -euo pipefail

echo "Setting up MileMind directory structure + CLAUDE.md files..."

# Directories
mkdir -p ".claude/agents"
mkdir -p ".claude/commands"
mkdir -p ".claude/skills/anthropic-tool-use"
mkdir -p ".claude/skills/exercise-science"
mkdir -p ".claude/skills/testing-patterns"
mkdir -p "backend/src/agents"
mkdir -p "backend/src/api"
mkdir -p "backend/src/deterministic"
mkdir -p "backend/src/evaluation"
mkdir -p "backend/src/tools"
mkdir -p "backend/tests/e2e"
mkdir -p "backend/tests/integration/agents"
mkdir -p "backend/tests/unit/deterministic"
mkdir -p "backend/tests/unit/tools"
mkdir -p "docs/architecture"
mkdir -p "frontend/mobile"
mkdir -p "frontend/web"

cat > "CLAUDE.md" << \EOF_CLAUDE_MD
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
- E2E: Full plan generation -> negotiation -> adaptation cycle
- Test files mirror source: `src/deterministic/banister.py` -> `tests/unit/deterministic/test_banister.py`

## Git Workflow
- Branch per feature: `feature/phase-{N}-{description}`
- Commit messages: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`
- Merge to main only after all phase gates pass

## When Compacting
Always preserve: list of modified files, current phase, test results, and any failing test details.
EOF_CLAUDE_MD

cat > "backend/CLAUDE.md" << \EOF_BACKEND_CLAUDE_MD
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
EOF_BACKEND_CLAUDE_MD

echo ""
echo "Done. Created:"
echo "  CLAUDE.md"
echo "  backend/CLAUDE.md"
echo "  Directory skeleton (.claude/, backend/, frontend/, docs/)"
echo ""
echo "You still need to:"
echo "  1. Copy PRD into docs/"
echo "  2. git add -A && git commit"
echo "  3. git checkout -b feature/phase-1-banister"
echo "  4. claude  <- let it create agents, skills, commands, settings"
