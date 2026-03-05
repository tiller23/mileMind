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
5. Repeat up to `max_retries` (default 5)

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

### Tools Available
All five deterministic tools are exposed to the planner:

| Tool | Purpose | When to call |
|------|---------|-------------|
| `compute_training_stress` | TSS for a single workout | Every workout |
| `evaluate_fatigue_state` | CTL/ATL/TSB from training history | Fatigue checks |
| `validate_progression_constraints` | ACWR + load increase safety | Before finalizing |
| `simulate_race_outcomes` | Finish-time Monte Carlo | If VDOT available |
| `reallocate_week_load` | Adjust weekly schedule | Load rebalancing |

### Planning Workflow
The prompt instructs the planner to follow a specific sequence:

1. **Analyze** the athlete profile (goals, fitness, constraints)
2. **Design macrocycle** — assign weeks to phases (BASE → BUILD → PEAK → TAPER)
3. **Propose workouts** for each week, calling `compute_training_stress` for every workout
4. **Validate progression** by calling `validate_progression_constraints` on weekly loads
5. **Adjust and retry** if validation fails
6. **Simulate race** outcomes if VDOT data is available

### Output Format
The planner must produce a JSON block with this structure:
- `athlete_name`, `goal_event`, `goal_date`
- `weeks[]` — each with `week_number`, `phase`, `workouts[]`, `target_load`, `notes`
- Each workout has `day`, `workout_type`, `distance_km`, `pace_zone`, `duration_minutes`, `intensity`, `tss`, `description`
- `predicted_finish_time_minutes` (from tool or null)

### Safety Rules
Hard constraints the planner must respect:
- Rest days mandatory (1/week min, 2 for <=5 training days)
- 80/20 intensity distribution (80% easy, 20% hard)
- Long run cap (default 30% of weekly distance)
- Progressive overload (default max 10% increase/week)
- Recovery weeks every 3-4 building weeks
- Injury-aware workout selection
- ACWR ceilings by risk tolerance (conservative: 1.2, moderate: 1.3, aggressive: 1.5)

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
| Safety | 2x | >= 70 | Rest days, 80/20, ACWR, injuries, long run cap |
| Progression | 1x | >= 70 | Load increases, step-back weeks, phase transitions |
| Specificity | 1x | >= 70 | Goal-appropriate workouts, phase-appropriate |
| Feasibility | 1x | >= 70 | Realistic durations, volumes, intensities |

**Overall score** = (safety×2 + progression + specificity + feasibility) / 5

Any dimension below 70 → automatic rejection.

### Review Workflow
1. Read the plan
2. Spot-check 2-3 claims with tools (re-compute TSS, re-validate progression)
3. Score each dimension (0-100)
4. Write concise critique
5. List specific issues
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
3. **Previous plan** — the rejected plan text
4. **Reviewer critique** — the textual assessment
5. **Specific issues** — bulleted list of actionable fixes
6. **Revision instructions:**
   - Address EVERY issue
   - Re-run `compute_training_stress` for modified workouts
   - Re-run `validate_progression_constraints` on revised loads
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
