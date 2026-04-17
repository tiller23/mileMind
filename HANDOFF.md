# Session Handoff — 2026-04-16 (end of day)

**Branch:** `main` — clean, nothing pending.
**Tests:** 57 frontend + 308 backend strength/api/agents — all passing. tsc + ruff + black clean.
**Status:** Three merges to main today. Feature/strength-polish is done; dedup sweep done; live-test feedback fixes done.

## What landed on main today

### `174d7f8` — feat: strength polish pass 2

- `/strength` acute-injury gate rewritten as a persistent caution banner.
  Blocks always render; no dismiss button, no dead empty state. Backend
  route (`backend/src/api/routes/strength.py`) stopped short-circuiting
  `blocks=[]` when acute is flagged.
- New `StrengthCallout` component placed on dashboard + plan detail for
  discoverability. Copy varies on `profile.injury_tags.length`.
- Planner + reviewer prompts (`backend/src/agents/prompts.py`) carve
  strength content out of the plan JSON — `/strength` playbook now owns
  strength prescriptions exclusively. Saves tokens; kills the "plan
  bottom overlaps with strength page" duplication.

### `1128820` — refactor: dedupe frontend constants

- Deleted unused `ChartBarIcon` + `UserGroupIcon`.
- `lib/units.ts` now exports `MILES_TO_KM` (derived from `KM_TO_MILES`).
  Onboarding imports it. Fixed three stale `0.621371` literals in
  dashboard + StravaConnect to use the shared constant.
- New `lib/enums.ts` — `GOAL_OPTIONS` / `GOAL_LABELS` / `RISK_LABELS` /
  `RISK_OPTIONS`. `RISK_LABELS` typed as `Record<RiskTolerance, string>`
  so removing a variant is a compile error.
- New `lib/workouts.ts` — `WORKOUT_TYPE_LABELS` + `formatWorkoutType`.
  PlanCalendar and dashboard both import from here. Dashboard's 7-type
  inline formatter was upgraded to the 11-type shared map, so
  `cross_train` / `repetition` / `marathon_pace` now display with
  canonical labels rather than title-cased fallback.

### `13e2f56` — fix: strength page UX polish

From Tyler's live test on main:

- **2 exercises per block by default** (was 1). Toggle reveals the rest.
  Module-level `DEFAULT_VISIBLE_EXERCISES = 2` for easy tuning.
- **Onboarding current-injury checkbox copy fix.** The old
  `I have a <strong>current</strong> injury right now` had a JSX
  whitespace issue around the inline `<strong>` that made "current" and
  "injury" visually fuse on some layouts. Rewrote without the bold, and
  updated copy to match the new caution-banner behavior:
  `"I have an active injury right now (not just past history). We'll
  add a 'see a PT first' reminder at the top of your strength playbook."`
- **Cache fix:** `useUpsertProfile` now uses `removeQueries` for
  `["strength-playbook"]` instead of `invalidateQueries`. The 5-minute
  `staleTime` was causing a visible flash of stale blocks (old banner
  state) after toggling `current_acute_injury`. Dropping the cache
  forces a clean refetch on next `/strength` mount.

## Backlog surfaced this session

### Not urgent but worth tracking

1. **Backend `≥2 exercises per block` invariant is not enforced in tests.**
   Per-block minimum today is 3 (posterior_chain after worst-case
   contraindication filtering), so `slice(0, 2)` is always safe. If the
   catalog is ever trimmed, a block could drop to 1 and the "Show 0 more"
   edge case reappears. Add a unit test in `backend/tests/unit/strength/`
   asserting every block has ≥ 2 exercises across all `InjuryTag`
   combinations of size ≤3.

2. **Demo plan JSONs have stale strength content.** Files in
   `backend/src/demo/plans/*.json` still have strength routines embedded
   in `supplementary_notes`, which the prompt carve-out now forbids.
   Decision needed: regenerate with the new prompt, or leave as static
   seeds (they're demo fixtures, not production). No tests reference the
   specific strength content, so leaving them is low-risk drift.

3. **Inline profile editor latent concern.** `useUpsertProfile` uses
   `removeQueries(["strength-playbook"])`. If someone later adds an
   inline profile editor *on* `/strength` itself, saving the form would
   rip data out from under the open page. Comment is in the hook already
   — next reviewer should see it. Onboarding is the only current editor
   and it navigates to `/dashboard` on success, so not an issue today.

4. **Backend dupe/unused sweep.** Today's sweep was heavy on frontend.
   Explore agent didn't turn up backend findings, but the pass was light
   — a targeted second pass could find unused Python exports, dead API
   routes, or repeated prompt-prose that should be template-ized.

5. **Extract `BlockExerciseList` component.** The IIFE in
   `strength/page.tsx` around lines 184–210 is functional but slightly
   ugly. Pulling it into its own component with local `useState` would
   drop the `expandedBlocks` dictionary in the parent. Pure refactor,
   low value.

### Product followups (from memory, still relevant)

- **Units toggle** — miles/km preference exists in the profile but prompt
  outputs still need to honor it.
- **Tempo paces** — show actual pace targets from VDOT on planned workouts.

## Suggested next session starter

Pick one:

- **Backend dupe/unused sweep** (item #4 above) — mechanical cleanup,
  similar payoff to today's frontend pass.
- **Units toggle implementation** — feature-shaped work, user-facing.
- **Plan generation quality check** — open question whether the new
  prompt carve-out changes plan quality. Might warrant a run through the
  eval harness to compare scores before/after. `backend/evaluation_reports/`
  has the last report for baseline comparison.

## Commands

```bash
# Backend — strength + agents + api
cd backend && /Users/tylerdavis/anaconda3/envs/milemind/bin/python \
  -m pytest tests/unit/strength/ tests/unit/api/ tests/unit/agents/ -q

# Frontend
cd frontend/web && npm test -- --run

# Typecheck
cd frontend/web && npx tsc --noEmit

# Backend lint
cd backend && /Users/tylerdavis/anaconda3/envs/milemind/bin/ruff check src/ tests/ \
  && /Users/tylerdavis/anaconda3/envs/milemind/bin/black --check src/ tests/

# Dev servers
cd backend && /Users/tylerdavis/anaconda3/envs/milemind/bin/python \
  -m uvicorn src.api.main:create_app --factory --reload
cd frontend/web && npm run dev
```

## Conventions (standing)

- No `Co-Authored-By` on commits.
- Push to remote after every commit.
- Code review (via `code-reviewer` subagent) before every commit —
  fix all CRITICAL/WARNING/SUGGESTION findings before committing.
- `frontend/web/AGENTS.md`: Next.js has breaking changes from training
  data; read `node_modules/next/dist/docs/` before writing Next-specific
  code.
- Pre-commit hooks: `pip install pre-commit && pre-commit install`.
