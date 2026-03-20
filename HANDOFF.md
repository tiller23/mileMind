# Phase 5: Consumer Frontend + Real Data

**Status:** 5a complete, 5b next
**Branch:** `feature/phase-5a-db-api`
**Tests:** 1783 passing (36 new)
**Date:** 2026-03-19

## Phase 5a Completed
- SQLAlchemy ORM: 7 tables (users, athlete_profiles, training_plans, workout_logs, jobs, chat_messages, strava_tokens)
- Async sessions with SQLite fallback for tests
- FastAPI app with CORS, lifespan hooks
- JWT auth: access (15min) + refresh (30d) via httpOnly cookies
- Google OAuth callback with email_verified check
- Profile CRUD (GET/PUT, upsert pattern)
- Plan routes (list, get, debug, archive)
- Pydantic request/response schemas
- Alembic configured (sync engine for migrations)
- Security: JWT secret production validator, no info disclosure, Pydantic validation on all inputs
- Code reviewed: 5 CRITICALs fixed, 6 WARNINGs fixed

---

## Goal

Build the full web dashboard, API layer, database, and data integrations so real athletes can use MileMind. Everything through Phase 4 runs in a CLI/eval harness -- Phase 5 makes it a product.

---

## Architecture Overview

```
Browser (Next.js)
    |
    v
FastAPI  ───>  PostgreSQL (JSONB)
    |
    ├── /api/auth/*         (JWT + OAuth)
    ├── /api/athletes/*     (CRUD profiles)
    ├── /api/plans/*        (generate, list, get)
    ├── /api/strava/*       (OAuth callback, sync)
    └── /api/debug/*        (agent reasoning log)
    |
    v
Orchestrator (existing) ───> Claude API
    |
    v
Deterministic Engine (existing)
```

---

## Sub-phases

### 5a: Database + API Layer
**Priority: Must-have foundation -- everything else depends on this.**

1. **PostgreSQL schema + migrations**
   - `users` table (id, email, hashed_password, created_at)
   - `athlete_profiles` table (user_id FK, profile JSONB, created_at, updated_at)
   - `training_plans` table (user_id FK, plan JSONB, approved bool, scores JSONB, decision_log JSONB, created_at)
   - `strava_tokens` table (user_id FK, access_token, refresh_token, expires_at)
   - Use Alembic for migrations. Never edit migration files directly.

2. **FastAPI routes**
   - `POST /api/auth/register` — email/password signup
   - `POST /api/auth/login` — JWT token issuance
   - `GET /api/athletes/me` — get current user's profile
   - `PUT /api/athletes/me` — update profile
   - `POST /api/plans/generate` — trigger orchestrator (async task)
   - `GET /api/plans` — list user's plans
   - `GET /api/plans/{id}` — get plan with decision log
   - All routes require JWT auth. Input validation via Pydantic (already built).

3. **Async plan generation**
   - Plan generation takes 30-120s. Use background tasks (or Celery/ARQ).
   - `POST /api/plans/generate` returns 202 + job_id.
   - `GET /api/plans/status/{job_id}` polls completion.
   - On completion, persist to `training_plans` table.

**Key files to create:**
- `backend/src/api/main.py` — FastAPI app with CORS, middleware
- `backend/src/api/routes/auth.py`
- `backend/src/api/routes/athletes.py`
- `backend/src/api/routes/plans.py`
- `backend/src/api/deps.py` — dependency injection (db session, current user)
- `backend/src/db/models.py` — SQLAlchemy models
- `backend/src/db/session.py` — async engine + session factory
- `backend/alembic/` — migration directory

**Tests:**
- Unit tests for each route (mock orchestrator)
- Integration tests with test database
- Auth flow tests (register, login, token refresh, invalid token)

---

### 5b: Next.js Web Dashboard
**Priority: Must-have -- the thing users actually see.**

1. **Pages**
   - `/` — Landing page with value prop
   - `/login`, `/register` — Auth pages
   - `/onboarding` — Conversational wizard (goal, fitness, injuries, risk)
   - `/dashboard` — Main view: current plan calendar, weekly overview
   - `/plan/{id}` — Plan detail: week-by-week, workout cards, scores
   - `/plan/{id}/debug` — Agent reasoning view (decision log, tool calls, retry chain)
   - `/settings` — Profile editor, Strava connection, preferences

2. **Key components**
   - `WeekView` — Calendar-style weekly layout with workout cards
   - `WorkoutCard` — Day's workout: type, distance, zone, duration, TSS
   - `ScoreBadge` — Safety/progression/specificity/feasibility badges
   - `PlanGenerationLoader` — "Agents collaborating" animation during generation
   - `ChatPanel` — Natural language plan adjustments (stretch goal for 5b)

3. **Data fetching**
   - Use React Query (TanStack Query) for API calls + caching
   - JWT stored in httpOnly cookie or localStorage
   - Poll `/api/plans/status/{job_id}` during generation

**Key files to create:**
- `frontend/web/src/app/` — Next.js App Router pages
- `frontend/web/src/components/` — Shared UI components
- `frontend/web/src/lib/api.ts` — API client (fetch wrapper with auth)
- `frontend/web/src/lib/types.ts` — TypeScript types matching backend models

**Tests:**
- Component tests with vitest + React Testing Library
- No `any` types (CLAUDE.md constraint)

---

### 5c: Strava Integration
**Priority: Should-have -- key differentiator, but app works without it.**

1. **OAuth2 flow**
   - `GET /api/strava/connect` — redirect to Strava authorization
   - `GET /api/strava/callback` — exchange code for tokens, store in DB
   - Token refresh on expiry (Strava tokens expire every 6 hours)

2. **Activity sync**
   - `POST /api/strava/sync` — pull recent activities
   - Webhook subscription for real-time activity notifications
   - Map Strava activities to MileMind workout format (distance, duration, HR, pace)
   - Compute TSS from imported activities using deterministic engine

3. **Baseline estimation**
   - Import last 6-8 weeks of activities on connect
   - Compute CTL/ATL/TSB from historical data
   - Auto-populate AthleteProfile fields (weekly_volume, vdot estimate from race results)

**Key files to create:**
- `backend/src/api/routes/strava.py`
- `backend/src/integrations/strava.py` — Strava API client
- `backend/src/integrations/activity_mapper.py` — Strava -> MileMind workout

---

### 5d: Deployment
**Priority: Must-have -- needs to be publicly accessible.**

1. **Backend deployment**
   - Dockerize FastAPI app
   - PostgreSQL managed instance (Railway, Supabase, or Neon)
   - Environment variables for all secrets (API keys, DB URL, JWT secret)
   - Health check endpoint

2. **Frontend deployment**
   - Vercel for Next.js (free tier works)
   - Environment variables for API URL

3. **CI/CD**
   - GitHub Actions: lint + test on PR, deploy on main merge
   - Test database for CI (SQLite or test PostgreSQL)

---

## Prompt Tuning Notes (from eval feedback)

These observations from Phase 4 eval runs should inform Phase 5 work:

- **Zone 3 is easy side of 80/20** — already fixed in prompts (intensity <= 0.82)
- **Too much Zone 2 for experienced runners** — user noted plans feel overly conservative. Consider adding tempo pace discovery (e.g., 2-mile time trial) to generate personalized paces.
- **Decimal intensity values feel abstract to users** — zones are better. Consider showing zone names prominently in the UI with intensity as a tooltip/detail.
- **Recovery week every 4 building weeks** — already set as default in prompts.
- **Plans look good for normal people** — 2/2 approved first attempt for recreational runners. Edge cases (advanced marathoner) need more work on max_tokens for long plans.

---

## Execution Order

```
5a (API + DB)  ──────────>  5b (Frontend)  ──>  5d (Deploy)
                              |
5c (Strava)  ────────────────┘
```

5a is the foundation. 5b and 5c can be parallelized once 5a is solid. 5d comes last.

---

## Definition of Done

- [ ] User can register, log in, create a profile
- [ ] User can generate a training plan and see it in the dashboard
- [ ] Plan detail view shows week-by-week calendar with workout cards
- [ ] Agent reasoning debug view shows decision log and scores
- [ ] Strava OAuth connects and imports activity history
- [ ] App deployed to a public URL
- [ ] All existing 1747+ backend tests still pass
- [ ] Frontend tests pass with no `any` types
- [ ] No API keys or secrets in committed code
- [ ] Sub-30-second plan generation (or clear loading state if longer)
