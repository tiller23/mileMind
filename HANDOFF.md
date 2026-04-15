# Session Handoff — 2026-04-14

**Branch:** `main`
**Tests:** 1953 backend + 56 frontend = 2009 total
**Status:** DEPLOYED — strength training playbook live at `milemind.app/strength`

## What Shipped This Session

### Strength Training Playbook (new feature)
- `/strength` page: deterministic running-specific exercise selection driven by injury tags + goal + experience tier
- LLM (Haiku) only writes block rationale blurbs, with static fallbacks on API failure or prescriptive-language drift
- Server-enforced PT gate when `current_acute_injury=true` (returns `blocks=[]` so direct API callers can't bypass)
- 5 blocks: posterior chain, single-leg stability, hip/glute, calf/Achilles, core anti-rotation (last is conditional on goal distance + injury tags)
- ~28 exercises in catalog, tagged with equipment + difficulty + injury beneficial/contraindicated
- Onboarding extended: injury-tag chip multi-select + acute-injury toggle with optional description
- Cost: ~$0.001 per playbook view (Haiku, with cache + in-flight dedupe)

### Lint Hygiene (structural fix)
- `.pre-commit-config.yaml` added — ruff + black on backend, `tsc --noEmit` on frontend
- CI expanded to lint `tests/` (was `src/` only)
- Per-file ruff ignores for tests (legitimate Mock/PascalCase)
- Documented in CLAUDE.md
- **Setup once per clone:** `pip install pre-commit && pre-commit install`

### Pass-2 Hardening (from second-round code review)
- Narrative cache: in-flight Future map deduplicates concurrent calls (no thundering herd)
- `/strength` rate limit: 10/min per user
- `/profile` PUT rate limit: 20/min per user (bounds rapid profile-shape cycling)
- Migration: dialect-aware JSONB default (`'[]'::jsonb` on Postgres)
- Removed `InjuryTag.NONE` footgun
- Profile mutation invalidates `["strength-playbook"]` query

### Misc
- `notes/` folder gitignored (personal craft notes — see directory for current contents)

## Prod Testing Findings — Strength Page (Tyler's notes from live test)

These are the items to address NEXT SESSION. Page works, no rollback needed — polish + UX pass.

1. **"Tailored for: shin_splints"** uses raw enum value, not natural-language label. Need a label map (`shin_splints → "Shin Splints"`, `it_band → "IT Band"`, etc.) on the frontend block badge.
2. **PT-gate state is misleading at first glance.** The user-facing copy / framing of the held/gated state isn't clear enough on first read. Worth rewriting and possibly redesigning the visual hierarchy.
3. **Overlap with the bottom of the plan page.** Tyler's note: "that with the bottom bit on the plan kind of overlap if that makes sense" — open both pages side-by-side and figure out whether it's a thematic overlap (strength content duplicating plan content) or a literal layout collision.
4. **Discoverability:** add a link to `/strength` from the dashboard and/or plan detail pages. Currently only reachable via the navbar, easy to miss.

## Open Items (carried from prior sessions)

### Should Do
1. Strava webhooks (still polling/manual sync; public URL available)
2. Monitor Railway logs
3. Verify Strava token encryption on prod

### Feature Backlog (ordered by value)
4. **Strength training polish** ← TOP, see findings above
5. Plan negotiation UI ("change up this week")
6. Plan adaptation loop — feed actual Strava workouts back into planner
7. Bidirectional Strava sync (push planned workouts)
8. Mobile app (React Native/Expo)

### Prompt Tuning Backlog
9. Recovery week load reduction tied to athlete level
10. Zone 3 "easy" classification nuance
11. Workout variety enforcement in reviewer
12. User-selectable experience level

## Known Issues
- Railway port: custom domain targets 8080, not 8000
- `DATABASE_URL` had trailing whitespace on first paste — watch on future edits
- Strava webhooks not yet implemented

## Local Dev Setup
```bash
# One-time:
pip install pre-commit && pre-commit install

# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Conda env: `milemind` (Python 3.12). PostgreSQL with `milemind` database, Google OAuth + Strava creds in `backend/.env`.

## Notes (`notes/`, gitignored)
Personal craft notes started this session — pair-on-notes pattern with Claude. Current files:
- `working-with-claude-code.md` — plan modes, two-pass review, subagent patterns
- `dev-workflow-lessons.md` — fix the system not the instances, cheap defenses beat clever ones
- `cross-session-prompt-escalation.md` — CC → web Claude → CC handoff pattern
- `adversarial-brainstorming.md` — "pick this apart" framing
