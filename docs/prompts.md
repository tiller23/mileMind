# MileMind Agent Prompts Reference

> **Source of truth:** `backend/src/agents/prompts.py`
> This document is a readable companion — if it diverges from the code, trust the code.

## Architecture Overview

MileMind uses a multi-agent architecture to generate training plans:

```
Athlete Profile
      |
      v
  [Planner Agent]  ──tool calls──>  [Deterministic Engine]
      |                                    |
      v                                    v
  Training Plan                    TSS, CTL, ACWR, etc.
      |
      v
  [Reviewer Agent]  ──spot-checks──>  [Deterministic Engine]
      |
      v
  Approve / Reject
      |
      ├── Approved → return plan
      └── Rejected → critique + issues → back to Planner
```

The **Orchestrator** (`backend/src/agents/orchestrator.py`) drives the loop:
1. Planner generates a plan
2. Phase 2 validation pre-filters structural issues
3. Reviewer scores across 4 dimensions
4. If rejected, planner revises using critique
5. Repeat up to `max_retries` (default 3)

---

## Planner System Prompt

**Used by:** `PlannerAgent` in `backend/src/agents/planner.py`
**When:** Every `messages.create()` call during plan generation

### Role
The planner is an expert running coach that designs periodized training plans.
It uses coaching expertise for _decisions_ and deterministic tools for _numbers_.

### Critical Constraints
The core invariant of MileMind — the LLM never invents physiological values:

1. **Must use tools** for all metrics (TSS, CTL, ATL, TSB, ACWR, VO2max, VDOT, paces)
2. **Un-sourced numbers get rejected** by the reviewer
3. **Role boundary:** planner = coaching decisions, tools = math

### Safety Rules (Positioned BEFORE Workflow)
Hard constraints the planner must respect. These appear before the planning
workflow in the prompt to ensure they are read first and applied throughout:

- **Progressive overload limits** — max weekly load increase (default 10%). This is
  the #1 reason plans get rejected.
- **Recovery weeks mandatory** — every 3-4 building weeks. Plans without them are rejected.
- **Rest days mandatory** (1/week min, 2 for <=5 training days)
- **Phase transitions must be smooth** — no load spikes at phase boundaries
- **80/20 intensity distribution** — Seiler's polarized model (Seiler, 2010). 80% Zone 1-2, 20% hard.
- **Long run cap** (default 30% of weekly distance)
- **ACWR ceilings** by risk tolerance (conservative: 1.2, moderate: 1.3, aggressive: 1.5)

### Athlete-Level Coaching Guidelines
Plans are adapted based on the athlete's level (auto-classified from VDOT + base mileage):

| Level | VDOT | Base | Workout Types | Key Differences |
|-------|------|------|---------------|-----------------|
| Beginner | < 35 | < 25 km/wk | Zone 1-2 base, strides/short tempo in build | No VO2max intervals early. Walk-run OK. Simplicity. |
| Intermediate | 35-50 | 25-60 km/wk | Tempo/threshold in build, intervals in peak | Zone 3 long runs OK. Full workout variety in build+. |
| Advanced | > 50 | > 60 km/wk | Full variety from build phase | Progression long runs, double threshold days. |

### Pace Zone System (Zone 1-6)
Mapped to Daniels training paces and heart rate zones:

| Zone | Name | Intensity | %VO2max | Use For |
|------|------|-----------|---------|---------|
| Zone 1 | Recovery | 0.55-0.65 | 55-65% | Recovery runs, warm-up/cool-down |
| Zone 2 | Easy/Aerobic | 0.65-0.74 | 65-74% | Base building, easy runs, most long runs |
| Zone 3 | Marathon/Moderate | 0.75-0.82 | 75-82% | Marathon pace, progression runs |
| Zone 4 | Threshold | 0.83-0.88 | 83-88% | Tempo runs, threshold intervals |
| Zone 5 | Interval/VO2max | 0.95-1.00 | 95-100% | VO2max intervals, race-specific |
| Zone 6 | Repetition | 1.05-1.20 | >100% | Speed/form work, short reps |

**Long runs are NOT always Zone 2.** Intermediate+ athletes benefit from Zone 3
segments (e.g., progression long runs). Even beginners can do Zone 2-3 long runs
after a base phase.

### Injury History Guidelines
Nuanced approach instead of blanket restrictions:
- **Past (healed):** Add strengthening exercises in supplementary notes. No mileage reduction.
- **Recent/current:** Reduce aggravating movements, suggest cross-training alternatives.
- **Chronic/recurring:** Caution with the specific movement pattern only.

### Tools Available
All six deterministic tools are exposed to the planner:

| Tool | Purpose | When to call |
|------|---------|-------------|
| `compute_training_stress` | TSS for a single workout | Every workout |
| `evaluate_fatigue_state` | CTL/ATL/TSB from training history | Fatigue checks |
| `validate_progression_constraints` | ACWR + load increase safety | After EACH PHASE |
| `simulate_race_outcomes` | Finish-time Monte Carlo | If VDOT available |
| `reallocate_week_load` | Adjust weekly schedule | Load rebalancing |
| `project_taper` | CTL/ATL/TSB during taper or optimal taper length | Taper planning |

### Planning Workflow
The prompt instructs the planner to follow a specific sequence:

1. **Analyze** the athlete profile (goals, fitness, level, constraints)
2. **Design macrocycle with recovery weeks first** — mark recovery weeks before filling training weeks
3. **Propose workouts** for each week, calling `compute_training_stress` for every workout
4. **Validate progression AFTER EACH PHASE** — don't wait until the end
5. **Adjust and retry** if validation fails
6. **Simulate race** outcomes if VDOT data is available
7. **Project taper** for plans with taper phase

### User Message Structure
The user message now includes:
- Athlete Profile (JSON)
- **Athlete Level** (BEGINNER/INTERMEDIATE/ADVANCED) — references coaching guidelines
- **Safety Constraints (Hard Limits)** — max weekly increase %, recovery week mandate
- Instructions with zone-based pace zone instruction

### Output Format
The planner must produce a JSON block with this structure:
- `athlete_name`, `goal_event`, `goal_date`
- `weeks[]` — each with `week_number`, `phase`, `workouts[]`, `target_load`, `notes`
- Each workout has `day`, `workout_type`, `distance_km`, `pace_zone` (Zone 1-6), `duration_minutes`, `intensity`, `tss`, `description`
- `predicted_finish_time_minutes` (from tool or null)
- `supplementary_notes` — strengthening exercises, cross-training suggestions

### Efficiency
The prompt instructs batch tool calls to minimize round-trips. Target: 5-8 turns per plan.

---

## Reviewer System Prompt

**Used by:** `ReviewerAgent` in `backend/src/agents/reviewer.py`
**When:** Every `messages.create()` call during plan review

### Role
Independent evaluator. Has NOT seen the planner's reasoning — evaluates the
plan purely on its output merits.

### Critical Constraints
Same core invariant, but from the verification side:

1. **Must verify claims** with tool calls — never accept values at face value
2. **Never generate numbers** — call tools to check
3. **Role boundary:** reviewer = score/critique/approve/reject, not redesign

### Evaluation Dimensions

| Dimension | Weight | Threshold | What it measures |
|-----------|--------|-----------|------------------|
| Safety | 2x | >= 70 | Rest days, 80/20 (Seiler), ACWR, injuries, long run cap |
| Progression | 1x | >= 70 | Load increases, step-back weeks, phase transitions |
| Specificity | 1x | >= 70 | **Level-appropriate** workouts, phase-appropriate |
| Feasibility | 1x | >= 70 | Realistic durations, volumes, intensities |

**Overall score** = (safety×2 + progression + specificity + feasibility) / 5

Any dimension below 70 → automatic rejection.

### Level-Aware Specificity (New)
The reviewer now evaluates specificity relative to the athlete's level:
- **Beginners:** Should NOT have VO2max intervals early. Simplicity is a feature.
  Do NOT penalize for lacking advanced workout types.
- **Intermediate:** Should have tempo/threshold in build, intervals in peak.
- **Advanced:** Full variety, sophisticated periodization expected.

### Long Run Assessment (New)
- Zone 3 segments within long runs are normal for intermediate+ athletes.
- Only penalize if long runs are at Zone 4+ for majority of distance.
- Beginners can do Zone 2-3 long runs after base phase.

### Injury History Assessment (New)
- Past healed injuries → expect strengthening notes, NOT blanket restrictions.
- Recent/current → expect reduced aggravating movements.
- Chronic → caution with specific movement pattern only.

### Review Workflow
1. Read the plan
2. Spot-check 2-3 claims with tools (re-compute TSS, re-validate progression)
3. Score each dimension (0-100)
4. Write concise critique
5. List specific, actionable issues (e.g., "Week 4 load increases 25%, must be <= 10%")
6. Output JSON verdict

### Output Format
```json
{
  "approved": true|false,
  "scores": {"safety": N, "progression": N, "specificity": N, "feasibility": N},
  "critique": "2-3 sentence assessment",
  "issues": ["Actionable fix 1", "Actionable fix 2"]
}
```

---

## Revision Prompt Template

**Used by:** `PlannerAgent._build_revision_message()` in `backend/src/agents/planner.py`
**When:** The orchestrator sends a rejected plan back to the planner for revision

### Structure
The revision message contains:
1. **Rejection notice** — "Your previous plan was REJECTED"
2. **Athlete profile** — full JSON (same as initial request)
3. **Athlete level** — BEGINNER/INTERMEDIATE/ADVANCED
4. **Safety constraints (hard limits)** — max weekly increase, recovery week mandate
5. **Previous plan** — the rejected plan text (truncated at 50k chars)
6. **Reviewer critique** — the textual assessment (truncated at 10k chars)
7. **Specific issues** — bulleted list of actionable fixes
8. **Revision instructions:**
   - Address EVERY issue
   - Re-run `compute_training_stress` for modified workouts
   - Re-run `validate_progression_constraints` — validate AFTER EACH PHASE
   - Use Zone 1-6 pace zones
   - Return complete revised plan as JSON
   - Do NOT just patch — regenerate with corrections

---

## Review Request Template

**Used by:** `ReviewerAgent._build_review_message()` in `backend/src/agents/reviewer.py`
**When:** The orchestrator sends a plan to the reviewer for evaluation

### Structure
The review message contains:
1. **Athlete profile** — full JSON
2. **Training plan** — the planner's output text
3. **Tool usage summary** — what tools the planner called (name + OK/FAIL)
4. **Instructions:**
   - Spot-check 2-3 key claims with tools
   - Score each dimension 0-100
   - Reject if any score below 70
   - Return verdict as JSON block

---

## Key Design Decisions

### Why separate prompts?
The reviewer has NOT seen the planner's reasoning. This is intentional — it
prevents the reviewer from being anchored by the planner's justifications and
forces independent evaluation.

### Why tool verification?
The reviewer can call the same tools to independently verify claims. If the
planner says "TSS = 45.2", the reviewer can re-compute it and flag discrepancies.
This catches cases where the planner fabricates or misuses tool results.

### Why safety weighted 2x?
An unsafe plan that reaches an athlete could cause injury. Other dimensions
(specificity, feasibility) are important for plan quality but less critical
for athlete safety. The 2x weight ensures safety issues dominate the overall score.

### Why 70 threshold?
Below 70 indicates significant issues that should be addressed. The threshold
is a balance: too low and bad plans slip through, too high and plans rarely
get approved (causing expensive retry loops).

### Why level-aware specificity?
The original prompt said "5K plans should include VO2max sessions" which created
a no-win scenario: the planner got penalized for NOT including VO2max work
(specificity), then penalized for including it for a beginner (safety). Level-aware
evaluation resolves this by matching expectations to the athlete's capabilities.

### Why safety rules before workflow?
In the first eval run, the planner ignored safety rules positioned at the bottom
of the prompt. Moving them before the workflow ensures they're read first and
applied throughout plan generation, rather than being an afterthought.

### Why numbered pace zones?
Labels like "easy" and "repetition" are ambiguous. Zone 1-6 maps directly to
Daniels training paces and heart rate zones, giving athletes a consistent
framework. Each zone has both a number AND a name for clarity.

### Phase 5 TODO: User-selectable experience level
Currently the athlete level is auto-classified from VDOT + weekly base. In Phase 5,
users should be able to self-select their experience level, with the auto-classification
as a default. This prevents misclassification when users don't have VDOT data or have
atypical profiles.
