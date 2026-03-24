# Session Handoff — 2026-03-24

**Branch:** `feature/phase-5c-frontend`
**Tests:** 1703 backend + 48 frontend = 1751 total
**Date:** 2026-03-24

## What Got Done This Session

### Plan Duration & Start Date
- `plan_duration_weeks` field on profile (8-24 weeks, default 12)
- `plan_start_date` on plan generation request (defaults to next Monday)
- Adjustable start date on existing plans via PATCH endpoint + dashboard UI
- "This Week" card uses plan_start_date for accurate week calculation
- Alembic migration for new column

### Pre-Generation Confirmation Panel
- Clicking "New Plan" shows profile summary (goal, mileage, duration, days, approach)
- Start date picker inline
- "Need to update your profile first?" link
- Cancel/Generate buttons — no more accidental API calls

### Plan Generation State Management
- `GET /jobs/active` endpoint — detects running jobs
- Dashboard resumes loader when navigating away and back
- Loader shows "Click here if not redirected" fallback
- `onComplete` clears job state + refreshes plan list
- Unapproved plans show "Draft Plan" warning with regenerate link

### Prompt Overhaul
- STOP safety checkpoint gates in planning workflow (structure → distance → safety)
- Distance differentiation rules: long run ≥1.5x easy, varied easy run distances, work-only quality distances
- Recovery week bounce-back exception: 10% rule applies building→building only
- Reviewer scoring rubric (90-100 excellent → 0-39 broken)
- Critique length uncapped for better revision feedback
- Critical rules reinforced in user message, not just system prompt
- Better output examples showing proper differentiation
- Max retries 3→4

### Frontend Polish
- Today highlight on dashboard "This Week" card and full plan calendar
- Tappable workout cells on dashboard — shows full description, zone, distance, duration
- Current week highlighted on full plan calendar with "Current" label
- Mobile responsive: horizontal scroll calendar, stacking grids, responsive headers
- Removed tokens/cost from plan detail (debug view only)
- Number inputs clear properly (no stuck 0 on mileage/training days)
- Miles/km conversion on profile save/load (stores km, displays miles when imperial)

### Infrastructure
- JWT access token 15→60 min (prevents logout during SSE plan generation)
- CORS allows PATCH method
- Updated `docs/prompts.md` reference doc

## Test Counts
- Backend: 1703
- Frontend: 48 (5 test files)

## Next Session

### Should Do
1. **Mobile responsiveness testing** — changes are in, needs real-device verification
2. **Better error/404 pages** — generic pages for route misses
3. **Test plan generation end-to-end** — verify prompt changes produce better plans (varied distances, proper long runs, quality workout descriptions)

### Feature Backlog
4. Phase 5d — Strava integration
5. Phase 5e — Deployment (Docker, managed Postgres, Vercel)

### Prompt Tuning Backlog (from external audit)
6. Recovery week load reduction tied to athlete level (currently flat 20-30%)
7. Zone 3 "easy" classification nuance for standalone marathon-pace workouts
8. Workout variety enforcement in reviewer (rotation check across weeks)
9. User-selectable experience level (currently auto-classified)

## Local Dev Setup
```bash
# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Requires: PostgreSQL with `milemind` database, Google OAuth creds in `backend/.env`
