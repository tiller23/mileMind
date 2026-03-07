# MileMind CLI Reference

Two CLIs: the **main CLI** generates training plans, and the **eval harness CLI** benchmarks the pipeline across synthetic personas.

## Setup

1. Set your API key:
   ```
   export ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
   Or create `backend/.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

2. Install dependencies:
   ```bash
   cd backend
   pip install -e ".[dev]"
   ```

All commands below run from the `backend/` directory.

---

## Main CLI (`src.cli`)

Generate a training plan for a single athlete.

### Quick start

```bash
# Dry run — inspect prompts, tools, profile (no API calls)
python -m src.cli --example beginner --dry-run

# Generate a plan (prompts for confirmation)
python -m src.cli --example beginner

# Skip confirmation
python -m src.cli --example beginner -y
```

### Built-in example profiles

| Profile | Athlete | Goal | Base | Risk |
|---------|---------|------|------|------|
| `beginner` | Sarah Chen | 5K, 30 min | 15 km/wk | conservative |
| `intermediate` | Marcus Okoro | marathon, 3:30 | 65 km/wk | moderate |
| `advanced` | Elena Rodriguez | marathon, 3:00 | 90 km/wk | moderate |
| `aggressive` | David Kim | marathon, 2:50 | 105 km/wk | aggressive |

### Change types

```bash
# Full plan with reviewer loop (default, ~$0.52-1.56)
python -m src.cli --example beginner --change-type full -y

# Adaptation — lightweight review, 1 retry (~$0.52)
python -m src.cli --example beginner --change-type adaptation -y

# Tweak — planner only, no reviewer (~$0.17)
python -m src.cli --example beginner --change-type tweak -y
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--example` | — | Built-in profile: `beginner`, `intermediate`, `advanced`, `aggressive` |
| `--profile` | — | Path to a custom athlete JSON file |
| `--dry-run` | off | Print what would be sent without calling the API |
| `--change-type` | `full` | `full`, `adaptation`, or `tweak` |
| `--model` | `claude-sonnet-4-20250514` | Planner model |
| `--reviewer-model` | `claude-opus-4-20250514` | Reviewer model |
| `--max-iterations` | 15 | Agent loop iteration cap |
| `--max-retries` | 3 | Planner-reviewer retry cycles |
| `-y, --yes` | off | Skip confirmation prompt |
| `-v, --verbose` | off | DEBUG-level logging |
| `--debug` | off | Show tool call trace in output |

### Custom athlete profiles

```json
{
  "name": "Your Name",
  "age": 30,
  "weekly_mileage_base": 40.0,
  "goal_distance": "half_marathon",
  "goal_time_minutes": 105.0,
  "vdot": 45.0,
  "risk_tolerance": "moderate",
  "training_days_per_week": 5,
  "injury_history": ""
}
```

Optional fields: `hr_max`, `hr_rest`, `vo2max`, `long_run_cap_pct`, `max_weekly_increase_pct`.

---

## Eval Harness CLI (`src.evaluation.run`)

Benchmark the planner-reviewer pipeline across 5 synthetic personas.

### Quick start

```bash
# Dry run — see personas and config
python -m src.evaluation.run --dry-run

# Run all 5 personas (Opus reviewer, ~$2.60-5.20)
python -m src.evaluation.run

# Run one persona to sanity check (~$0.50)
python -m src.evaluation.run --persona beginner_runner

# Sonnet-vs-Opus comparison (runs all personas twice, ~$4-8)
python -m src.evaluation.run --compare

# Batch API mode — 50% cheaper, slower (~$1.30-2.60)
python -m src.evaluation.run --batch

# JSON output for scripting
python -m src.evaluation.run --json
```

### Personas

| ID | Athlete | Goal | Risk | Why |
|----|---------|------|------|-----|
| `beginner_runner` | Sarah | 5K | conservative | Baseline safe plan |
| `advanced_marathoner` | Marcus | marathon | moderate | Periodization quality |
| `aggressive_spiker` | Jake | marathon | aggressive | Dangerous 30→42km jump |
| `injury_prone_runner` | Maria | 50K ultra | conservative | Injury history respect |
| `overtrained_athlete` | Chris | half marathon | conservative | Overtraining detection |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--persona` | all 5 | One or more persona IDs to run |
| `--planner-model` | `claude-sonnet-4-20250514` | Planner model |
| `--reviewer-model` | `claude-opus-4-20250514` | Reviewer model |
| `--compare` | off | Run Sonnet-vs-Opus comparison |
| `--batch` | off | Use Batch API (50% cheaper, async) |
| `--output-dir` | `evaluation_reports/` | Report output directory |
| `--dry-run` | off | List config without running |
| `--json` | off | JSON output to stdout + `.json` file |
| `--max-retries` | 3 | Orchestrator retry cycles |
| `--max-tokens` | 1,000,000 | Per-persona token budget |
| `-v, --verbose` | off | DEBUG-level logging |

### Output

Reports are written to `evaluation_reports/`:

- `plan_review_report.md` — per-persona results, scores, cost breakdown
- `plan_review_report.json` — (with `--json`) machine-readable results
- `comparison_report.md` — (with `--compare`) side-by-side Sonnet vs Opus
- `FEEDBACK.md` — template for manual review notes

---

## Cost Reference

| Scenario | Est. Cost |
|----------|-----------|
| Single plan, tweak (no reviewer) | ~$0.17 |
| Single plan, full (1 cycle) | ~$0.52 |
| Single plan, full (worst case 3 cycles) | ~$1.56 |
| Eval harness, all 5 personas | ~$2.60-5.20 |
| Eval harness, all 5 with batch | ~$1.30-2.60 |
| Eval harness, Sonnet-vs-Opus compare | ~$4-8 |
| Token budget hard cap (1M tokens) | ~$7.50 |
