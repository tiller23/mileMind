# MileMind API Cost Optimization Strategy

## Current State (Phase 3)

| Metric | Value |
|--------|-------|
| Cost per cycle (Sonnet planner + Opus reviewer) | ~$0.52 |
| Typical run (1-2 cycles) | $0.52 - $1.04 |
| Hard budget cap (1M tokens) | ~$7.50 |
| Reviewer share of cost | ~67% |

## Production Target

~$0.05-$0.10 per plan generation at scale (10K+ users).

Current cost is ~5-10x too high for a consumer subscription product.
The path to get there is a combination of architectural changes (build now)
and operational changes (flip later).

---

## Optimization Levers

### 1. Prompt Caching (build now)

**What:** Anthropic's prompt caching stores repeated prompt prefixes server-side.
Cached input tokens cost 90% less ($0.30/M instead of $3/M for Sonnet,
$1.50/M instead of $15/M for Opus).

**Why it matters:** Our system prompts are ~2,000 tokens and identical across
every call. The tool schemas are another ~1,500 tokens. That's 3,500 tokens
per call that we're paying full price for repeatedly.

**Savings estimate:**
- Current: 3,500 cached-eligible tokens x ~10 calls/cycle = 35,000 tokens at full price
- With caching: 35,000 tokens at 10% price
- Sonnet savings per cycle: ~$0.09 (input drops from $0.084 to ~$0.009)
- Opus savings per cycle: ~$0.12 (input drops from $0.135 to ~$0.014)
- **Total savings: ~$0.21/cycle (~40% reduction)**

**Architecture needed:**
- Set `cache_control` headers on system prompt and tool definition blocks
- Anthropic API supports this via `cache_control: {"type": "ephemeral"}` on
  message content blocks
- Our `_run_agent_loop` in both planner.py and reviewer.py constructs messages
  fresh each call — need to mark the system prompt block as cacheable
- The ToolRegistry already serializes tools via `get_anthropic_tools()` — mark
  these as cacheable too

**Code change scope:** Small. Add cache_control to the system message and tools
array in `_run_agent_loop`. No architectural changes needed — just API params.

**When to build:** Phase 5 (when we have real API calls running regularly).
But design the message construction now so it's easy to add.

---

### 2. Conditional Review / Risk-Based Routing (build now)

**What:** Not every plan needs a full Opus review. A plan tweak (swapping one
workout) is lower risk than a full 16-week marathon plan from scratch.

**Why it matters:** The reviewer is 67% of the cost. Skipping it for low-risk
operations cuts cost from $0.52 to $0.17.

**Risk tiers:**

| Tier | Example | Review needed? | Cost |
|------|---------|---------------|------|
| **Full generation** | New 16-week plan | Yes (full review) | ~$0.52 |
| **Revision** | Reviewer feedback loop (already in orchestrator) | Yes | ~$0.52 |
| **Adaptation** | Missed a workout, adjust next week | Lightweight check | ~$0.25 |
| **Tweak** | Swap easy run for cross-training | Skip review | ~$0.17 |

**Architecture needed:**
- `PlanChangeType` enum: `FULL`, `ADAPTATION`, `TWEAK`
- Orchestrator accepts a `change_type` parameter
- `TWEAK` → planner only, no reviewer (already supported via `--no-review`)
- `ADAPTATION` → reviewer with reduced iterations (e.g., max_iterations=3)
- `FULL` → current behavior

**Code change scope:** Medium. Add enum, add routing logic to Orchestrator.run().
The `--no-review` CLI flag already proves the planner-only path works.

**When to build:** Now. The enum and routing belong in the orchestrator design.
The API layer (Phase 5) will need this to decide which path to take.

---

### 3. Batch API for Non-Interactive Workloads (design now)

**What:** Anthropic's Batch API processes requests asynchronously at 50% cost.
Results come back within 24 hours (usually much faster).

**Why it matters:** Many plan generation scenarios aren't real-time:
- Weekly plan refresh (can run overnight)
- Evaluation harness (Phase 4 — runs dozens of synthetic athletes)
- Pre-computing plans for new signups based on common profiles

**Savings estimate:**
- Batch pricing: 50% of standard
- A $0.52 cycle becomes $0.26
- Phase 4 evaluation with 5 synthetic athletes x 3 cycles each = $7.80 → $3.90

**Architecture needed:**
- Batch-compatible message formatting (same format, different endpoint)
- Async result polling or webhook handler
- The orchestrator's `run()` method is already async — batch is a different
  transport, not a different logic flow
- Need a `BatchOrchestrator` or a `batch=True` flag on the existing one

**Code change scope:** Medium-large. Separate transport layer from orchestration
logic. The current orchestrator mixes "call Claude" with "process results" —
separating these makes batch possible.

**When to build:** Phase 4 (evaluation harness is the first real batch use case).
Design the separation now so the orchestrator isn't tightly coupled to
synchronous API calls.

---

### 4. Response Caching / Deduplication (build now)

**What:** Cache plan outputs keyed by athlete profile hash. If the same profile
requests a plan and nothing has changed, return the cached result.

**Why it matters:** In production, many requests will be redundant:
- User opens the app, sees their plan, closes it, opens it again
- Multiple users with identical profiles (common for beginners)
- Re-running after a crash or timeout

**Architecture needed:**
- Hash function over athlete profile + any modification context
- Cache layer (in-memory for dev, Redis/PostgreSQL for prod)
- TTL-based expiry (plans are valid for ~1 week)
- Cache-bust on: new workout logged, profile change, manual refresh

**Code change scope:** Small-medium. Add a cache check before `orchestrator.run()`
at the API layer. The orchestrator itself stays pure — caching is a concern of
the caller.

**When to build:** Phase 5 (needs the API layer). But the hash function over
athlete profiles can be built now alongside the domain models.

---

### 5. Model Swap / Distillation (config change, later)

**What:** Replace Opus reviewer with Sonnet. Long-term, distill planner behavior
into a fine-tuned smaller model.

**Why it matters:**
- Sonnet reviewer: cycle cost drops from $0.52 to ~$0.20
- Fine-tuned Haiku planner: cycle cost drops to ~$0.03-$0.05

**Architecture needed:** Already built. Model is a constructor parameter on both
PlannerAgent and ReviewerAgent. Swapping is a one-line change.

**Validation needed before swapping:**
- Run Phase 4 evaluation harness with Sonnet reviewer
- Compare approval rates, score distributions, and constraint violations
- If Sonnet catches the same issues Opus does, swap it

**When to build:** Phase 4 (evaluation harness provides the data to validate).
The code is already ready — this is a data-driven decision, not a code change.

---

## Combined Savings Projection

| Optimization | Per-cycle savings | Cumulative cost |
|-------------|-------------------|-----------------|
| Baseline (current) | — | $0.52 |
| + Prompt caching | -$0.21 | $0.31 |
| + Conditional review (skip for tweaks) | -$0.14 avg | $0.17-$0.31 |
| + Batch API (where applicable) | -50% | $0.09-$0.16 |
| + Sonnet reviewer | -$0.12 | $0.05-$0.10 |
| + Response caching | -variable | < $0.05 effective |

**Production target of $0.05-$0.10 is achievable** with these optimizations
stacked. No single optimization gets there alone.

---

## Real-World Per-User Cost Model

Based on a typical runner training for a race (half marathon, marathon, etc.),
checking their plan before each workout, making occasional adjustments.

### Typical user behavior

| Action | Weekly freq | Change type | Cost each | Weekly cost |
|--------|------------|-------------|-----------|-------------|
| View plan (before workout) | 5-6x | **$0 (cached)** | $0 | $0 |
| View plan (post-workout check) | 3-4x | **$0 (cached)** | $0 | $0 |
| Swap a workout | 1-2x | TWEAK | $0.17 | $0.17-$0.34 |
| Missed day / reschedule | 0.5-1x | ADAPTATION | $0.52 | $0.26-$0.52 |
| Full plan regen | 0.25x (~1/month) | FULL | $0.52-$1.04 | $0.13-$0.26 |

### Monthly cost per user

| Scenario | Monthly API cost |
|----------|-----------------|
| **Light user** (views only, rare changes) | ~$0.50-$1.00 |
| **Active user** (regular tweaks + adaptations) | ~$1.72-$4.48 |
| **Power user** (frequent changes, regens) | ~$4.00-$7.00 |
| **Average across user base** (estimated) | ~$2.00-$3.50 |

### Over a full training cycle (16 weeks)

| User type | Total API cost |
|-----------|---------------|
| Light | $2-$4 |
| Active | $7-$18 |
| Power | $16-$28 |

### What this means for pricing

At a **$10-15/month subscription**, API costs as a % of revenue:

| Optimization stage | Avg monthly cost | % of $12/mo sub |
|-------------------|-----------------|-----------------|
| **Current** (Opus reviewer) | ~$2.00-$3.50 | 17-29% |
| + Prompt caching | ~$1.20-$2.10 | 10-18% |
| + Sonnet reviewer | ~$0.70-$1.80 | 6-15% |
| + All optimizations | ~$0.30-$0.70 | 2-6% |

**Key insight:** The caching layer is critical. Most user interactions are
*viewing* the plan, not generating it. Without caching, every app open costs
$0.52. With caching, views are free and only actual changes incur API costs.
The difference between a viable product and a money pit is whether we cache.

### Comparison to competitors

| Product | Monthly price | AI cost model |
|---------|--------------|---------------|
| TrainingPeaks | $20/mo | No AI, fully deterministic |
| Whoop coaching | $30/mo | AI included, proprietary model |
| ChatGPT Plus | $20/mo | Unlimited queries (subsidized) |
| **MileMind target** | $10-15/mo | ~$2-3.50/user current, <$1 optimized |

MileMind's cost structure is viable at $10-15/month IF we implement the
caching and prompt optimization layers. Without them, margins are too thin
at current Opus pricing.

---

## What to Build Now (Phase 3-4) vs Later (Phase 5+)

### Build the patterns now
- [x] `PlanChangeType` enum and risk-based routing in Orchestrator
- [x] Athlete profile hashing (for future cache keys)
- [x] `MessageTransport` Protocol — separates API calls from agent logic
  (enables batch and mock transports)
- [ ] Ensure system prompts and tool schemas are constructed once, not per-call

### Flip switches later
- [ ] Enable `cache_control` on API calls (Phase 5, one-line addition)
- [ ] Add response cache at API layer (Phase 5, needs Redis/DB)
- [ ] Switch reviewer to Sonnet (Phase 4, after evaluation validates it)
- [ ] Batch API for evaluation harness (Phase 4)
- [ ] Fine-tuning / distillation (Phase 5+, needs production data)

---

## Cost Monitoring

Track per-run costs via the `DecisionLogEntry` token fields:
- `planner_input_tokens`, `planner_output_tokens`
- `reviewer_input_tokens`, `reviewer_output_tokens`

The `OrchestrationResult` aggregates these. Log them to PostgreSQL in Phase 5
for dashboards and alerts. Set up alerts for:
- Single run exceeding $2
- Daily cost exceeding $50 (at scale, adjust based on user count)
- Average cost per run trending upward (prompt regression)
