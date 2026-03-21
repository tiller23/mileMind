# Phase 5c: Next.js Frontend

**Status:** 5c initial build complete, needs review
**Branch:** `feature/phase-5c-frontend`
**Tests:** 1814 backend + 15 frontend = 1829 total
**Date:** 2026-03-20

## Completed Phases
- **5a:** Database + API (7 tables, auth, profile, plans, Alembic)
- **5b:** Plan generation + SSE (JobManager, progress callbacks, streaming)
- **5c:** Next.js frontend (pages, components, API client, auth flow)

## Phase 5c Built
- Next.js 16 with App Router, TypeScript, Tailwind CSS
- Landing page with value prop and feature highlights
- Google OAuth login flow (redirect -> callback -> dashboard)
- Onboarding wizard (athlete profile form with all fields)
- Dashboard with plan list, generate button, SSE progress loader
- Plan detail page with scores, token usage, plan text
- Debug view with full agent decision log per iteration
- API client with typed fetch wrapper + cookie auth
- TanStack Query hooks for all endpoints
- TypeScript types matching all backend Pydantic schemas
- Vitest + Testing Library setup with 15 tests
- frontend-reviewer agent created

## Local Dev Setup
```bash
# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Requires: PostgreSQL with `milemind` database, Google OAuth creds in `backend/.env`

## Next Up
- **Phase 5d:** Strava integration (OAuth, activity sync, baseline estimation)
- **Phase 5e:** Deployment (Docker, managed Postgres, Vercel, CI/CD)

## Definition of Done
- [x] User can register, log in, create a profile
- [x] User can generate a training plan and see it in the dashboard
- [ ] Plan detail view shows week-by-week calendar with workout cards
- [x] Agent reasoning debug view shows decision log and scores
- [ ] Strava OAuth connects and imports activity history
- [ ] App deployed to a public URL
- [x] All existing 1814 backend tests still pass
- [x] Frontend tests pass with no `any` types
- [x] No API keys or secrets in committed code
- [x] Clear loading state during plan generation (SSE loader)
