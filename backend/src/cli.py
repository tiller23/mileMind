"""MileMind CLI — test plan generation from the command line.

Usage:
    # From a JSON athlete profile file:
    python -m src.cli --profile athlete.json

    # Quick test with a built-in example profile:
    python -m src.cli --example beginner

    # With debug output (shows tool calls):
    python -m src.cli --example intermediate --debug

    # Dry run (inspect what would be sent without calling API):
    python -m src.cli --example beginner --dry-run

    # Skip confirmation prompt:
    python -m src.cli --example beginner -y

    # Planner-only mode (skip reviewer):
    python -m src.cli --example beginner --no-review -y

Requires ANTHROPIC_API_KEY in backend/.env or environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.agents.orchestrator import Orchestrator, OrchestrationResult
from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.prompts import PLANNER_SYSTEM_PROMPT
from src.agents.validation import ValidationResult
from src.models.athlete import AthleteProfile, RiskTolerance
from src.models.decision_log import ReviewOutcome
from src.tools.registry import ToolRegistry

# Load .env from backend/ directory (where CLI is run from)
load_dotenv()

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
        help="Claude model to use for planner (default: claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed tool call trace",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the system prompt, tools, and athlete profile without calling the API",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the confirmation prompt before making API calls",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=30,
        help="Maximum agent loop iterations per planner/reviewer call (default: 30)",
    )
    # Phase 3: reviewer flags
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Skip the reviewer agent (planner-only mode, Phase 2 behavior)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum planner-reviewer retry cycles (default: 5)",
    )
    parser.add_argument(
        "--reviewer-model",
        type=str,
        default=None,
        help="Claude model for reviewer (default: same as --model)",
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
    """Pretty-print the planner result (Phase 2 planner-only mode).

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


def print_orchestration_result(result: OrchestrationResult, debug: bool = False) -> None:
    """Pretty-print the orchestration result (Phase 3 multi-agent mode).

    Shows the plan, decision log with per-iteration scores, and convergence
    statistics.

    Args:
        result: The orchestration output.
        debug: Whether to show detailed per-iteration data.
    """
    print("\n" + "=" * 70)
    print("MILEMIND TRAINING PLAN (Multi-Agent)")
    print("=" * 70)

    if result.error:
        print(f"\n[ERROR] {result.error}")
    if result.warning:
        print(f"\n[WARNING] {result.warning}")

    if result.plan_text:
        print(f"\n{result.plan_text}")

    # --- Decision Log ---
    print("\n" + "-" * 70)
    print("DECISION LOG")
    print("-" * 70)
    for entry in result.decision_log:
        icon = {
            ReviewOutcome.APPROVED: "PASS",
            ReviewOutcome.REJECTED: "FAIL",
            ReviewOutcome.ERROR: "ERR ",
        }.get(entry.outcome, "????")
        print(f"\n  [{icon}] Attempt {entry.iteration}")

        if entry.scores:
            s = entry.scores
            print(
                f"         Scores: safety={s.safety} progression={s.progression} "
                f"specificity={s.specificity} feasibility={s.feasibility} "
                f"(overall={s.overall:.1f})"
            )
        if entry.critique:
            critique_display = entry.critique[:120]
            if len(entry.critique) > 120:
                critique_display += "..."
            print(f"         Critique: {critique_display}")
        if entry.issues:
            for issue in entry.issues[:3]:
                print(f"           - {issue}")
            if len(entry.issues) > 3:
                print(f"           ... and {len(entry.issues) - 3} more")

    # --- Final Scores ---
    if result.final_scores:
        print("\n" + "-" * 70)
        print("FINAL SCORES")
        print("-" * 70)
        s = result.final_scores
        print(f"  Safety:      {s.safety}/100 (2x weight)")
        print(f"  Progression: {s.progression}/100")
        print(f"  Specificity: {s.specificity}/100")
        print(f"  Feasibility: {s.feasibility}/100")
        print(f"  Overall:     {s.overall:.1f}/100")
        print(f"  All pass:    {'YES' if s.all_pass else 'NO'}")

    # --- Stats ---
    print("\n" + "-" * 70)
    print("STATS")
    print("-" * 70)
    print(f"  Approved:          {'YES' if result.approved else 'NO'}")
    print(f"  Attempts:          {len(result.decision_log)}")
    print(f"  Total iterations:  {result.total_iterations}")
    print(f"  Planner tokens:    {result.total_planner_tokens:,}")
    print(f"  Reviewer tokens:   {result.total_reviewer_tokens:,}")
    total_tokens = result.total_planner_tokens + result.total_reviewer_tokens
    print(f"  Total tokens:      {total_tokens:,}")
    print(f"  Elapsed:           {result.total_elapsed_seconds:.1f}s")

    # Rough cost estimate (Sonnet pricing: $3/M input, $15/M output approximation)
    est_cost = total_tokens * 0.000006  # rough average $/token
    print(f"  Est. cost:         ~${est_cost:.2f}")

    print()


def print_dry_run(
    athlete: AthleteProfile,
    model: str,
    max_iterations: int,
    review: bool = True,
    reviewer_model: str | None = None,
    max_retries: int = 5,
) -> None:
    """Print what would be sent to the API without making any calls.

    Args:
        athlete: The athlete profile to serialize.
        model: The Claude model identifier.
        max_iterations: The iteration cap.
        review: Whether reviewer is enabled.
        reviewer_model: The reviewer model (or None for same as planner).
        max_retries: Max planner-reviewer cycles.
    """
    from src.agents.planner import PlannerAgent

    print("\n" + "=" * 70)
    print("DRY RUN — no API calls will be made")
    print("=" * 70)

    print(f"\n  Planner model:  {model}")
    if review:
        print(f"  Reviewer model: {reviewer_model or model}")
        print(f"  Max retries:    {max_retries}")
    else:
        print(f"  Reviewer:       DISABLED (planner-only mode)")
    print(f"  Max iterations: {max_iterations}")
    if review:
        print(f"  Estimated cost: ~$0.50-1.50 (with reviewer)")
    else:
        print(f"  Estimated cost: ~$0.30-0.50 (planner only)")

    print("\n" + "-" * 70)
    print("SYSTEM PROMPT")
    print("-" * 70)
    print(PLANNER_SYSTEM_PROMPT)

    print("\n" + "-" * 70)
    print("TOOL DEFINITIONS")
    print("-" * 70)
    registry = ToolRegistry()
    from src.tools import compute_training_stress
    from src.tools import evaluate_fatigue_state
    from src.tools import validate_progression_constraints
    from src.tools import simulate_race_outcomes
    from src.tools import reallocate_week_load
    compute_training_stress.register(registry)
    evaluate_fatigue_state.register(registry)
    validate_progression_constraints.register(registry)
    simulate_race_outcomes.register(registry)
    reallocate_week_load.register(registry)

    for tool in registry.get_anthropic_tools():
        print(f"\n  {tool['name']}")
        schema = tool.get("input_schema", {})
        props = schema.get("properties", {})
        for prop_name, prop_def in props.items():
            req = " (required)" if prop_name in schema.get("required", []) else ""
            print(f"    - {prop_name}: {prop_def.get('type', '?')}{req}")

    print("\n" + "-" * 70)
    print("USER MESSAGE (athlete profile)")
    print("-" * 70)
    user_msg = PlannerAgent._build_user_message(athlete)
    print(user_msg)
    print()


async def main() -> None:
    """Main CLI entry point."""
    args = parse_args()

    # Load athlete profile
    athlete = load_athlete(args)
    review_enabled = not args.no_review
    reviewer_model = args.reviewer_model or args.model

    print(f"Generating plan for: {athlete.name}")
    print(f"  Goal: {athlete.goal_distance}", end="")
    if athlete.goal_time_minutes:
        print(f" in {athlete.goal_time_minutes:.0f} min")
    else:
        print()
    print(f"  Base mileage: {athlete.weekly_mileage_base} km/week")
    print(f"  Risk tolerance: {athlete.risk_tolerance.value}")
    print(f"  Planner model: {args.model}")
    if review_enabled:
        print(f"  Reviewer model: {reviewer_model}")
        print(f"  Max retries: {args.max_retries}")
    else:
        print(f"  Reviewer: DISABLED")

    # Dry run: show what would be sent and exit
    if args.dry_run:
        print_dry_run(
            athlete, args.model, args.max_iterations,
            review=review_enabled,
            reviewer_model=reviewer_model,
            max_retries=args.max_retries,
        )
        return

    # Confirmation prompt before spending API tokens
    if not args.yes:
        print(f"\n  Max iterations: {args.max_iterations}")
        if review_enabled:
            print(f"  Estimated cost: ~$0.50-1.50 (with reviewer)")
        else:
            print(f"  Estimated cost: ~$0.30-0.50 (planner only)")
        response = input("\nProceed with API call? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return

    if review_enabled:
        # Phase 3: Multi-agent orchestration
        print(f"\nStarting planner-reviewer orchestration...")

        try:
            orchestrator = Orchestrator(
                planner_model=args.model,
                reviewer_model=reviewer_model,
                max_retries=args.max_retries,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        result = await orchestrator.generate_plan(athlete)
        print_orchestration_result(result, debug=args.debug)

        if not result.approved or result.error:
            sys.exit(1)
    else:
        # Phase 2: Planner-only mode
        print(f"\nStarting planner agent (no review)...")

        start_time = time.monotonic()

        try:
            planner = PlannerAgent(model=args.model, max_iterations=args.max_iterations)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        planner_result = await planner.generate_plan(athlete)

        elapsed = time.monotonic() - start_time
        print(f"Completed in {elapsed:.1f}s")

        validation = planner_result.validation
        if validation is None:
            validation = ValidationResult(
                passed=False,
                issues=[planner_result.error or "Unknown error — validation not performed"],
            )

        print_result(planner_result, validation, debug=args.debug)

        if not validation.passed or planner_result.error:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
