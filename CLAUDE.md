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
- MUST: All API calls gated by token budget (1M default, ~$7.50 max). See `backend/CLAUDE.md` for full cost table.

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

## Session Startup
- On new sessions, run `git log --oneline -20` to understand recent work
- Check the Phase Progress section below for what's complete and what's next

## Phase Progress

### Completed
- **Phase 1: Deterministic Engine** — 5 models (banister, daniels, acwr, taper, monte_carlo) + training_stress. 286 unit tests, 100% coverage.
- **Phase 2: Tool Wrappers + Single Agent** — 5 tool wrappers, ToolRegistry, PlannerAgent, CLI, domain models. 929 tests total. Two code review rounds enforced deterministic boundary (all physiology math in src/deterministic/).
- **Phase 3: Multi-Agent Loop** — ReviewerAgent, Orchestrator, PlanChangeType routing (FULL/ADAPTATION/TWEAK), MessageTransport Protocol, AthleteProfile.cache_key(), decision logging, cost optimization patterns. 1046 tests total. Two code review rounds + cost analysis.
- **Phase 4: Evaluation Harness** — 7 synthetic personas (5 edge cases + 2 normal), HarnessRunner, BatchCoordinator (50% cost savings), markdown/PDF reports, CLI with --dry-run/--batch/--compare. Prompt injection sanitization, security hardening. 1747 tests total. Multiple code reviews + security audit.

### Next Up
- **Phase 5: Consumer Frontend + Real Data** — See `HANDOFF.md` for full plan. Next.js web dashboard, FastAPI routes, PostgreSQL, auth, Strava integration, cloud deployment.

## When Compacting
Always preserve: list of modified files, current phase, test results, and any failing test details.
