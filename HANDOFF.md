# Session Handoff — 2026-03-23

**Branch:** `feature/phase-5c-frontend`
**Tests:** 1830 backend + 48 frontend = 1878 total
**Date:** 2026-03-23

## What Got Done This Session

### Calendar View (Core Product View)
- `PlanCalendar` component — weeks as rows, days as columns, color-coded workout cells
- Click-to-expand workout details (description, distance, duration, TSS, intensity)
- Color legend, phase badges, week notes, row/column dividers
- Workout display names: "Fartlek" → "Mixed Pace", "Repetition" → "Speed Work"

### Backend: Structured Plan Storage
- Plans now stored as structured JSON (weeks/workouts) instead of `{"text": "..."}`
- `extract_structured_plan()` parses JSON from planner output
- `all_text` field on `AgentLoopResult` — captures text from ALL LLM turns (fixed bug where JSON block in earlier turn was lost)

### Miles/Km Unit Preference
- `preferred_units` field added to profile (domain model, DB model, API schemas, migration)
- Miles/Kilometers toggle on onboarding form
- `formatDistance()` utility converts km → mi for display
- Calendar, plan detail, dashboard all respect user's preference
- Planner prompt tells LLM to use preferred units in workout descriptions
- `distance_km` stays in km internally (deterministic engine consistency)

### Logo & Icons
- `Logo` component with M lettermark (size + variant props)
- `Icons.tsx` — SVG icon set (ShieldCheck, Beaker, Target, Eye, Runner, Shoe)
- Replaced all emoji usage across the app

### Design Polish
- Landing page: dark slate hero, gradient text, pill badge, gradient fade, proper icon cards
- Dashboard: "This Week" card with current week preview, welcome greeting, cleaner plan cards (removed scores/badges)
- Navbar: Logo component integrated
- All copy audit: 25+ changes across all pages (approved by user one-by-one)

### Prompt Fixes
- Single zones enforced (no "Zone 3-4")
- Restricted workout types (no fartlek/repetition)
- Removed stale `compute_training_stress` references from user message
- Added preferred units instruction to planner

### Cost Results
- First run with new prompts: $0.93 / 92K tokens (vs $5.37 / 960K before)
- Second run: $3.12 (variation expected, still well below old $5.37)

## Test Counts
- Backend: 1830
- Frontend: 48 (5 test files)

## Next Session

### Should Do
1. **Test plan generation with miles preference** — verify descriptions come back in miles
2. **Plan duration control** — let users pick 8/12/16 week plans
3. **Plan start date** — explicit field so "This Week" is more accurate than created_at estimate
4. **Remove token/cost from plan detail** — only show in debug view
5. **Mobile responsiveness check**

### Feature Backlog
6. Miles/km also for weekly mileage input (convert on save)
7. Better error/404 pages
8. Phase 5d — Strava integration
9. Phase 5e — Deployment

## Local Dev Setup
```bash
# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Requires: PostgreSQL with `milemind` database, Google OAuth creds in `backend/.env`
