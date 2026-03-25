# Session Handoff — 2026-03-25

**Branch:** `main` (Phase 5e merged)
**Tests:** 1904 backend + 54 frontend = 1958 total
**Date:** 2026-03-25
**Status:** DEPLOYED to production

## What Got Done This Session

### Phase 5e: Pre-Deployment Hardening & Deployment

#### Security Hardening
- Fernet encryption for Strava tokens at rest (`crypto.py`)
- Rate limiting via `slowapi` (auth 10/min, generate 5/hr, strava 20/min)
- SSE heartbeats every 15s to prevent Railway idle disconnect
- JWT logout revocation with denylist table + hourly cleanup
- Required `jti` claim on all tokens (no bypass for legacy tokens)
- Cookie domain support for cross-subdomain auth (`app.X` + `api.X`)

#### Access Controls
- Invite code system with atomic redemption (gates plan generation, not signup)
- Admin routes for invite code creation/listing (`POST/GET /invite/admin/codes`)
- Per-user monthly plan limit (2/month default)
- Global API budget cap ($50/month default)
- User role field (`user`/`admin`) with DB check constraint

#### Demo Mode
- 3 hand-crafted demo plans: beginner 5K (8wk), intermediate half (12wk), advanced marathon (16wk)
- Each includes realistic decision logs showing planner-reviewer negotiation
- Public API: `GET /demo/plans`, `/demo/plans/{id}`, `/demo/plans/{id}/debug` (no auth)
- Demo landing with persona cards and "How plans are built" section
- Reuses PlanCalendar and ScoreBadge components
- "View Demo Plans" button on landing page hero
- Seed script: `python scripts/seed_demo_data.py` (idempotent)

#### Deployment Infrastructure
- Backend Dockerfile (Python 3.12 slim, single Uvicorn worker, runs migrations on startup)
- GitHub Actions CI (backend tests + lint, frontend tests on push/PR)
- Production config: `ENVIRONMENT`, `COOKIE_DOMAIN`, `CORS_ORIGINS` fields
- Swagger docs disabled in production
- Security event logging for failed auth and rate limit hits

#### Security Pen Test (OWASP Top 10)
- 0 critical, 1 HIGH fixed, 4 MEDIUM fixed, 3 LOW fixed
- HIGH: `debug` flag can no longer bypass production secret validation
- Invite code entropy increased from 65K to ~2.8T keyspace
- `goal_distance` sanitized for prompt injection
- All findings documented and resolved before deploy

#### Production Deployment
- **Backend:** Railway (Docker, managed PostgreSQL, `api.milemind.app`)
- **Frontend:** Vercel (Next.js, `milemind.app`)
- **Domain:** `milemind.app` on Cloudflare (auto-connected to Railway)
- **Database:** Railway PostgreSQL (private networking)
- Google OAuth redirect URIs updated for production
- Strava callback domain updated for production
- Demo data seeded on production database

### Other Fixes
- Renamed `middleware.ts` to `proxy.ts` (Next.js 16 deprecation)
- Fixed Alembic migration chain (wrong `down_revision`)
- TypeScript null assertion fix for Strava OAuth callback
- Logo size prop fix in demo pages
- PlanCalendar/ScoreBadge prop mismatches fixed

## Production URLs
- **App:** https://milemind.app
- **API:** https://api.milemind.app
- **Health:** https://api.milemind.app/health
- **Demo:** https://milemind.app/demo

## Production Environment Variables (Railway)
- `DATABASE_URL` — asyncpg connection to Railway Postgres (private)
- `DATABASE_URL_SYNC` — sync connection for Alembic
- `JWT_SECRET` — generated, production-grade
- `STRAVA_TOKEN_ENCRYPTION_KEY` — Fernet key
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- `ANTHROPIC_API_KEY`
- `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET`
- `FRONTEND_URL` = `https://milemind.app`
- `COOKIE_DOMAIN` = `.milemind.app`
- `ENVIRONMENT` = `production`
- `DEBUG` = `false`

## Test Counts
- Backend: 1904 (48 new security/demo/invite tests)
- Frontend: 54

## Known Issues
- Railway port: custom domain targets 8080 (Railway's default PORT), not 8000
- `DATABASE_URL` had trailing whitespace on first paste — watch for this on future edits
- Strava webhooks not yet implemented (requires public URL, now available)

## Next Session

### Should Do
1. **Create invite codes** — run admin endpoint or script to generate codes for testers
2. **Strava token encryption key** — verify tokens are encrypted on production
3. **Monitor Railway logs** — watch for any startup issues or errors
4. **Strava webhooks** — now feasible with public URL `api.milemind.app`

### Feature Backlog
5. Plan negotiation UI ("change up this week")
6. Bidirectional Strava sync (push planned workouts)
7. Plan adaptation from actual workout data (feedback loop)
8. Mobile app (React Native/Expo)

### Prompt Tuning Backlog
9. Recovery week load reduction tied to athlete level
10. Zone 3 "easy" classification nuance
11. Workout variety enforcement in reviewer
12. User-selectable experience level

## Local Dev Setup
```bash
# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Requires: PostgreSQL with `milemind` database, Google OAuth + Strava creds in `backend/.env`
