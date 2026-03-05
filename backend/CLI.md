# MileMind CLI

Generate training plans from the command line using the planner agent.

## Setup

1. Create `backend/.env` with your API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

2. Install dependencies:
   ```bash
   cd backend
   pip install -e ".[dev]"
   ```

## Usage

All commands run from the `backend/` directory.

### Dry run (no API calls)

Inspect the system prompt, tool definitions, and athlete profile that would be sent:

```bash
python -m src.cli --example beginner --dry-run
```

### Generate a plan

```bash
# Built-in example profiles
python -m src.cli --example beginner        # Sarah — 5K, 15 km/week, conservative
python -m src.cli --example intermediate    # Marcus — marathon, 65 km/week, moderate
python -m src.cli --example advanced        # Elena — marathon, 90 km/week, injury history
python -m src.cli --example aggressive      # David — marathon, 105 km/week, aggressive

# From a custom JSON file
python -m src.cli --profile path/to/athlete.json
```

You'll be prompted to confirm before any API call is made. Skip with `-y`:

```bash
python -m src.cli --example beginner -y
```

### Debug mode

Show every tool call with inputs and outputs:

```bash
python -m src.cli --example intermediate --debug
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--example` | — | Use a built-in profile: `beginner`, `intermediate`, `advanced`, `aggressive` |
| `--profile` | — | Path to a custom athlete JSON file |
| `--dry-run` | off | Print what would be sent without calling the API |
| `--debug` | off | Show full tool call trace |
| `-y, --yes` | off | Skip confirmation prompt |
| `--model` | `claude-sonnet-4-20250514` | Claude model to use |
| `--max-iterations` | 10 | Cap on agent loop iterations |

## Custom athlete profiles

Create a JSON file matching the `AthleteProfile` schema:

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

## Cost

Each run uses Claude Sonnet (~$3/MTok input, ~$15/MTok output). A typical plan generation with ~40 tool calls across 6-10 iterations costs roughly $0.30-0.50.
