# Session Handoff — 2026-03-24 (Session 2)

**Branch:** `feature/phase-5c-frontend`
**Tests:** 1729 backend + 54 frontend = 1783 total
**Date:** 2026-03-24

## What Got Done This Session

### Phase 5d: Strava Integration
- OAuth connect/disconnect with JWT-signed CSRF state tokens
- `StravaService` — token exchange, auto-refresh (6-hour expiry), activity fetch
- Activity import with smart sync (only fetches new since last import, 1-hour overlap buffer)
- Dedup by `strava_activity_id`, unit conversion (m→km, s→min), run-only filter
- Safety: 30s httpx timeout, MAX_PAGES=20 pagination guard, 5-min sync cooldown
- `StravaConnect` component on onboarding page with "Powered by Strava" attribution
- Strava OAuth callback page (`/auth/callback/strava`)
- 6 REST endpoints: connect, callback, status, sync, disconnect, activities
- `StravaSyncResponse` includes `suggested_weekly_mileage_km` for profile enrichment
- 26 backend tests (service + routes), 6 frontend tests

### Plan vs. Actual on Dashboard
- Green actual distance overlay on This Week card (from Strava data)
- Tappable day cells show stacked Planned (gray) + Actual (green) detail panels
- Actual panel shows: activity name, distance, duration, avg HR, pace
- Days with only Strava data (no planned workout) show green-tinted cells
- Week navigation arrows (prev/next) with "Today" pill to snap back

### Security Hardening (Code Review Fixes)
- OAuth CSRF: state token now verified on Google callback (was generated but never checked)
- Middleware restored: `proxy.ts` → `middleware.ts`, function renamed
- `goal_distance` pattern constraint (`^[a-zA-Z0-9_ ]+$`) prevents prompt injection
- `weekly_mileage_base` capped at `le=500.0` km
- Pricing constants extracted to module level (`SONNET_INPUT_COST_PER_TOKEN` etc.)
- `StravaCallbackRequest.code` validated, response models typed (no bare dicts)

### Frontend Polish
- 404, error, global-error, and dashboard loading skeleton pages
- Navbar: keyboard nav (Escape closes dropdown), `role="menu"`/`role="menuitem"`
- Onboarding: unit toggle `role="radiogroup"` with `aria-checked`
- PlanCalendar: `aria-label` on workout cells, `WorkoutCell` memoized with `React.memo`
- `PlanGenerationLoader`: `useStableCallback` prevents SSE reconnects on parent render
- Date inputs: proper `htmlFor`/`id` and `aria-label` associations
- Logo SVGs updated to match Mm mark design (removed old winding path)
- `usePlan` accepts `undefined` instead of empty string

### Git Cleanup
- Removed stale files: `bootstrap.sh`, `proxy.ts`, 5 unused Next.js default SVGs
- Deleted 6 merged branches (local + remote): phase-3, phase-4-review-fixes, phase-5a-db-api, phase5-plan-cleanup, pre-phase5-hardening, security-warnings
- Only `main` and `feature/phase-5c-frontend` remain

## Test Counts
- Backend: 1729 (26 new Strava tests)
- Frontend: 54 (6 new Strava tests)

## Strava Setup
Strava is connected and working. Credentials in `backend/.env`:
- `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` from strava.com/settings/api
- Authorization callback domain: `localhost` (update for production)
- Redirect URI: `http://localhost:3000/auth/callback/strava`

## Known Deferrals
- Strava token encryption at rest → Phase 5e (deployment hardening)
- SSE cleanup race condition (60s timer) → Phase 5e (needs Redis)
- Strava webhooks for real-time sync → Phase 5e (needs public URL)
- Radiogroup arrow-key navigation → minor a11y enhancement
- `PlanData` index signature `[key: string]: unknown` → accepted tradeoff

## Next Session

### Should Do
1. **Merge to main** — Phase 5c+5d is feature-complete, all tests pass
2. **Phase 5e — Deployment** — Docker, managed Postgres, Vercel, Strava webhook setup
3. **Strava token encryption** — Fernet encryption with env key before production

### Feature Backlog
4. Strava webhooks for real-time activity sync (requires public URL)
5. Bidirectional Strava sync (push planned workouts)
6. Plan adaptation from actual workout data (feedback loop)
7. Mobile app (React Native/Expo)

### Prompt Tuning Backlog
8. Recovery week load reduction tied to athlete level
9. Zone 3 "easy" classification nuance for standalone marathon-pace workouts
10. Workout variety enforcement in reviewer
11. User-selectable experience level

## Local Dev Setup
```bash
# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Requires: PostgreSQL with `milemind` database, Google OAuth + Strava creds in `backend/.env`
