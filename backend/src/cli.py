"""MileMind CLI — test plan generation from the command line.

Usage:
    # From a JSON athlete profile file:
    python -m src.cli --profile athlete.json

    # Quick test with a built-in example profile:
    python -m src.cli --example beginner

    # With debug output (shows tool calls):
    python -m src.cli --example intermediate --debug

Requires ANTHROPIC_API_KEY environment variable to be set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.validation import ValidationResult
from src.models.athlete import AthleteProfile, RiskTolerance

# ---------------------------------------------------------------------------
# Built-in example profiles for quick testing
# ---------------------------------------------------------------------------

EXAMPLE_PROFILES: dict[str, dict] = {
    "beginner": {
        "name": "Sarah Chen",
        "age": 32,
        "weekly_mileage_base": 15.0,
        "goal_distance": "5K",
        "goal_time_minutes": 30.0,
        "vdot": 30.0,
        "risk_tolerance": "conservative",
        "training_days_per_week": 3,
        "injury_history": "",
    },
    "intermediate": {
        "name": "Marcus Okoro",
        "age": 41,
        "weekly_mileage_base": 65.0,
        "goal_distance": "marathon",
        "goal_time_minutes": 210.0,
        "vdot": 50.0,
        "hr_max": 179,
        "hr_rest": 52,
        "risk_tolerance": "moderate",
        "training_days_per_week": 5,
        "injury_history": "",
    },
    "advanced": {
        "name": "Elena Rodriguez",
        "age": 29,
        "weekly_mileage_base": 90.0,
        "goal_distance": "marathon",
        "goal_time_minutes": 180.0,
        "vdot": 58.0,
        "hr_max": 190,
        "hr_rest": 45,
        "risk_tolerance": "moderate",
        "training_days_per_week": 6,
        "injury_history": "IT-band issues 2024, shin splints 2023",
        "long_run_cap_pct": 0.25,
    },
    "aggressive": {
        "name": "David Kim",
        "age": 37,
        "weekly_mileage_base": 105.0,
        "goal_distance": "marathon",
        "goal_time_minutes": 170.0,
        "vdot": 62.0,
        "hr_max": 183,
        "hr_rest": 42,
        "risk_tolerance": "aggressive",
        "training_days_per_week": 6,
        "max_weekly_increase_pct": 0.15,
        "injury_history": "",
    },
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="MileMind CLI — generate a training plan from the command line",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--profile",
        type=str,
        help="Path to a JSON file containing an AthleteProfile",
    )
    group.add_argument(
        "--example",
        type=str,
        choices=list(EXAMPLE_PROFILES.keys()),
        help="Use a built-in example profile",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Claude model to use (default: claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed tool call trace",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=25,
        help="Maximum agent loop iterations (default: 25)",
    )
    return parser.parse_args()


def load_athlete(args: argparse.Namespace) -> AthleteProfile:
    """Load an AthleteProfile from CLI arguments.

    Args:
        args: Parsed CLI arguments.

    Returns:
        A validated AthleteProfile instance.
    """
    if args.example:
        data = EXAMPLE_PROFILES[args.example]
    else:
        path = Path(args.profile)
        if not path.exists():
            print(f"Error: profile file not found: {path}", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        return AthleteProfile.model_validate(data)
    except Exception as e:
        print(f"Error: invalid athlete profile: {e}", file=sys.stderr)
        sys.exit(1)


def print_result(
    result: PlannerResult, validation: ValidationResult, debug: bool = False,
) -> None:
    """Pretty-print the planner result.

    Args:
        result: The planner's output.
        validation: Pre-computed validation result.
        debug: Whether to show detailed tool call trace.
    """
    print("\n" + "=" * 70)
    print("MILEMIND TRAINING PLAN")
    print("=" * 70)

    if result.error:
        print(f"\n[ERROR] {result.error}")

    if result.plan_text:
        print(f"\n{result.plan_text}")

    print("\n" + "-" * 70)
    print("STATS")
    print("-" * 70)
    print(f"  Iterations:    {result.iterations}")
    print(f"  Tool calls:    {len(result.tool_calls)}")
    print(f"  Input tokens:  {result.total_input_tokens:,}")
    print(f"  Output tokens: {result.total_output_tokens:,}")
    print(f"  Total tokens:  {result.total_input_tokens + result.total_output_tokens:,}")

    if debug and result.tool_calls:
        print("\n" + "-" * 70)
        print("TOOL CALL TRACE")
        print("-" * 70)
        for i, tc in enumerate(result.tool_calls, 1):
            status = "OK" if tc["success"] else "FAIL"
            print(f"\n  [{i}] {tc['name']} [{status}]")
            print(f"      Input:  {json.dumps(tc['input'], indent=2)[:200]}")
            output_str = json.dumps(tc['output'], indent=2)
            if len(output_str) > 200:
                output_str = output_str[:200] + "..."
            print(f"      Output: {output_str}")

    print("\n" + "-" * 70)
    print("OUTPUT VALIDATION")
    print("-" * 70)
    if validation.passed:
        print("  PASSED — all physiological values grounded in tool calls")
    else:
        print("  FAILED:")
        for issue in validation.issues:
            print(f"    - {issue}")

    print()


async def main() -> None:
    """Main CLI entry point."""
    args = parse_args()

    # Load athlete profile
    athlete = load_athlete(args)
    print(f"Generating plan for: {athlete.name}")
    print(f"  Goal: {athlete.goal_distance}", end="")
    if athlete.goal_time_minutes:
        print(f" in {athlete.goal_time_minutes:.0f} min")
    else:
        print()
    print(f"  Base mileage: {athlete.weekly_mileage_base} km/week")
    print(f"  Risk tolerance: {athlete.risk_tolerance.value}")
    print(f"  Model: {args.model}")
    print(f"\nStarting planner agent...")

    start_time = time.monotonic()

    try:
        planner = PlannerAgent(model=args.model, max_iterations=args.max_iterations)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result = await planner.generate_plan(athlete)

    elapsed = time.monotonic() - start_time
    print(f"Completed in {elapsed:.1f}s")

    # generate_plan() already runs validate_plan_output() — reuse its result.
    validation = result.validation
    if validation is None:
        # Error-path results (API errors, etc.) have validation=None.
        # Create a minimal failed validation for display.
        validation = ValidationResult(
            passed=False,
            issues=[result.error or "Unknown error — validation not performed"],
        )

    print_result(result, validation, debug=args.debug)

    if not validation.passed or result.error:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
