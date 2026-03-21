# Session Handoff — 2026-03-21

**Branch:** `feature/phase-5c-frontend`
**Tests:** 1824 backend + 37 frontend = 1861 total
**Status:** Phase 5c polish + cost optimization complete, pending commit

## What Got Done This Session

### OAuth & Auth Fixes
- Fixed OAuth redirect URI mismatch (backend → `/auth/callback/google`)
- Fixed login flow — was navigating to JSON API endpoint, now fetches auth URL then redirects
- Fixed `secure=True` cookies blocking localhost — now conditional on HTTPS
- Added CSRF state parameter (generate → sessionStorage → validate on callback)
- Added error handling in auth callback (502 for Google errors, 500 for DB errors)
- Added auth guard hook (`useAuthGuard`) on all protected pages
- Added Next.js `proxy.ts` for server-side auth redirects
- Added 401 → automatic token refresh in API client

### SSE Resilience
- SSE connection drops now fall back to polling job status every 5 seconds
- Only shows "failed" if the job itself has failed status
- Fixed false "Generation failed" when plan actually completed (SSE timeout)

### Cost Optimization (Big One)
- **Post-processing**: New `plan_postprocess.py` computes TSS and target_load deterministically after LLM outputs plan — removes ~48 `compute_training_stress` tool calls per iteration
- **Prompt changes**: Planner no longer instructed to call compute_training_stress per workout. TSS fields removed from required output format. Reviewer no longer spot-checks TSS.
- **Validation update**: `compute_training_stress` no longer required in validation (TSS computed post-hoc)
- **Expected impact**: ~50% fewer tokens per plan generation, ~3-6 LLM turns instead of 8-12+

### Frontend Design
- Navbar: user dropdown menu with settings/logout, active link highlighting, sticky with backdrop blur
- Landing page: full redesign with gradient hero, how-it-works steps, feature cards, CTA, footer
- Login page: card design with gradient background
- Onboarding: sectioned form (About You / Your Running / Preferences) in white card
- Dashboard: skeleton loaders, better empty state with CTA, card shadows
- All cards: `rounded-xl` + `shadow-sm` + hover effects
- Geist font fix (was overridden by Arial)
- Running goal: added "General fitness" option, conditional goal time field
- Age field: no longer shows 0 when clearing
- Progress bar: darker track, static time estimate ("under 10 minutes"), tips rotation
- StatusBadge component for reusable badge patterns
- Exported `scoreColor` for testability

### Code Review Fixes
- OAuth CSRF state validation
- SSE JSON.parse guard (try/catch)
- Profile 404 returns null instead of throwing
- Typed `PlanData` interface
- Removed broken dark mode CSS vars
- Aria labels on spinners/status icons
- `usePlans` staleTime set to 60s

### Database
- Generated and ran initial Alembic migration (7 tables)

## Test Counts
- Backend: 1824 (was 1814, +10 for plan_postprocess tests + validation updates)
- Frontend: 37 (was 15, +22 for component/hook tests)

## Next Session

### Must Do
1. **Plan detail page redesign** — Parse structured JSON from `plan_data.text` and render week-by-week with expandable workout cards. Currently shows raw JSON dump. This is the core product view.
2. **Test the cost optimization** — Generate a plan and verify reduced token usage and cost vs the $5.37 plan from this session.

### Should Do
3. **Structured plan storage** — Store parsed plan JSON directly in `plan_data` instead of wrapping in `{"text": "..."}`. Backend change.
4. **Plan duration control** — Add `plan_weeks` field so users can request 8/12/16 week plans.

### Design Backlog
5. Score badges as mini progress bars on plan detail page
6. Dark navbar option (reviewer suggested, user hasn't weighed in)
7. Login split layout for desktop (branding panel + form panel)

### Phase 5d: Strava Integration
- Strava OAuth connect
- Activity sync + import history
- Baseline estimation from real data

### Phase 5e: Deployment
- Docker, managed Postgres, Vercel, CI/CD
