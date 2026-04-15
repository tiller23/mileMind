# Session Handoff — 2026-04-14

**Branch:** `feature/strength-training-planning` (current work)
**Tests:** 1924 backend + 54 frontend = 1978 total (as of commit b8fe37f)
**Status:** DEPLOYED to production — invite request flow + Strava auto-import live

## Current Production State

- **App:** https://milemind.app (Vercel)
- **API:** https://api.milemind.app (Railway + managed Postgres)
- **Demo:** https://milemind.app/demo (3 public plans, no auth)

## What's Shipped Since Phase 5e

### Invite Request Flow (commits `b8fe37f`, `31ec053`)
- `InviteRequest` model + migration with partial unique index (no duplicate pending)
- `POST /invite/request` — user-initiated request, 30-day deny cooldown, Discord webhook on new requests
- `GET /invite/request/status` — poll request state
- Admin endpoints: list / approve / deny (auto-assigns invite code on approve)
- Admin self-approval allowed; "invite-only" landing badge removed
- Resend transactional email on approval (HTML-escaped)
- Discord webhook URL validated against `discord.com/api/webhooks/` + markdown sanitized + mentions suppressed
- `has_invite`, `invite_request_status`, `role` exposed on `/auth/me`
- `InviteCodeBanner` component (request / pending / denied states)
- Dashboard gates plan creation behind `has_invite`
- Admin page at `/admin` with role guard
- Vercel Analytics added

### Code Quality (commits `5da45e0`, `553df53`)
- Ruff lint clean across backend; black formatted

## Strava Integration (already shipped in Phase 5d + 5e)
- OAuth connect flow, Fernet-encrypted tokens at rest
- **Auto-import**: `backend/src/services/strava.py:329` `import_activities()` pulls runs, dedupes by `strava_activity_id`, smart-sync since last import (75-day initial window + overlap buffer)
- Imported runs persist to `WorkoutLog` and overlay on plan calendar
- Rate limit: 20/min on `/strava/*`

## Active Work: Strength Training Feature

**Framing** (from prior design conversation):
- Running-specific strength assistant, NOT a general strength coach
- Education-heavy, recommendation-light v1
- Transparent reasoning (mirrors planner/reviewer pattern already trusted)
- Safety reviewer routes edge cases to "talk to a PT" instead of guessing
- Stay in running-science consensus (posterior chain, single-leg stability, hip/glute for IT band, etc.)

**Design doc to write:** `docs/strength-training-design.md` (TBD)

## Open Items

### Should Do
1. **Strava webhooks** — still polling/manual sync; public URL now available
2. Monitor Railway logs
3. Verify Strava token encryption on prod

### Feature Backlog (ordered by value)
4. **Strength training** ← active
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
# Backend (terminal 1)
cd backend && uvicorn src.api.main:create_app --factory --reload

# Frontend (terminal 2)
cd frontend/web && npm run dev
```

Requires: PostgreSQL with `milemind` database, Google OAuth + Strava creds in `backend/.env`
Conda env: `milemind` (Python 3.12)
