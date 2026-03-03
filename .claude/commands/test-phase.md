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
