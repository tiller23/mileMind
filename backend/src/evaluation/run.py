"""CLI entry point for the evaluation harness.

Usage:
    # Run all 5 personas with default models
    python -m src.evaluation.run

    # Run specific persona
    python -m src.evaluation.run --persona beginner_runner

    # Sonnet-vs-Opus comparison
    python -m src.evaluation.run --compare

    # Dry run (list personas, no API calls)
    python -m src.evaluation.run --dry-run

    # Custom reviewer model
    python -m src.evaluation.run --reviewer-model claude-sonnet-4-20250514
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from src.evaluation.personas import ALL_PERSONAS, list_persona_ids
from src.evaluation.report import generate_comparison_report, generate_plan_review_report
from src.evaluation.results import HarnessMetrics
from src.evaluation.runner import HarnessRunner


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="MileMind Evaluation Harness — benchmark the planner-reviewer pipeline",
    )
    parser.add_argument(
        "--persona",
        type=str,
        nargs="+",
        choices=list_persona_ids(),
        help="Run specific persona(s). Default: all 5.",
    )
    parser.add_argument(
        "--planner-model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Model ID for the planner (default: claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--reviewer-model",
        type=str,
        default="claude-opus-4-20250514",
        help="Model ID for the reviewer (default: claude-opus-4-20250514)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run Sonnet-vs-Opus reviewer comparison",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use Batch API for 50%% cost savings (slower, async processing)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evaluation_reports",
        help="Directory for output reports (default: evaluation_reports/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List personas and configuration without running",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Orchestrator max retries (default: 3)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1_000_000,
        help="Per-persona token budget (default: 1000000)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON to stdout and write a .json file alongside the .md report",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parsed = parser.parse_args()

    if parsed.compare and parsed.reviewer_model != "claude-opus-4-20250514":
        parser.error("--compare and --reviewer-model are mutually exclusive. "
                      "--compare runs both Opus and Sonnet automatically.")

    if parsed.batch and parsed.compare:
        parser.error("--batch and --compare are mutually exclusive. "
                      "Batch mode runs a single reviewer model concurrently.")

    return parsed


def _setup_logging(verbose: bool) -> None:
    """Configure logging for the harness run.

    Args:
        verbose: If True, set DEBUG level. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


async def run_single(args: argparse.Namespace) -> None:
    """Run the harness for a single reviewer model.

    Args:
        args: Parsed CLI arguments.
    """
    runner = HarnessRunner(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        planner_model=args.planner_model,
        reviewer_model=args.reviewer_model,
        max_retries=args.max_retries,
        max_total_tokens=args.max_tokens,
    )

    start = time.monotonic()
    if args.batch:
        results = await runner.run_all_batched(persona_ids=args.persona)
    else:
        results = await runner.run_all(persona_ids=args.persona)
    total_elapsed = time.monotonic() - start

    metrics = runner.compute_metrics(results, total_elapsed_seconds=total_elapsed)

    # Write report
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = generate_plan_review_report(results, metrics)
    report_path = output_dir / "plan_review_report.md"
    report_path.write_text(report)

    if getattr(args, "json_output", False):
        json_data = {
            "metrics": metrics.to_dict(),
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(json_data, indent=2))
        json_path = output_dir / "plan_review_report.json"
        json_path.write_text(json.dumps(json_data, indent=2))
        print(f"JSON report written to: {json_path}", file=sys.stderr)
    else:
        print()
        print(metrics.summary())
        print()
        print(f"Plan review report written to: {report_path}")


async def run_comparison(args: argparse.Namespace) -> None:
    """Run the Sonnet-vs-Opus comparison.

    Args:
        args: Parsed CLI arguments.
    """
    runner = HarnessRunner(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        planner_model=args.planner_model,
        max_retries=args.max_retries,
        max_total_tokens=args.max_tokens,
    )

    start = time.monotonic()
    comparison_results = await runner.run_comparison(persona_ids=args.persona)
    total_elapsed = time.monotonic() - start

    # Compute metrics once per model
    model_metrics: dict[str, HarnessMetrics] = {}
    for model, results in comparison_results.items():
        model_metrics[model] = HarnessMetrics.from_results(
            results, reviewer_model=model,
            planner_model=args.planner_model,
            total_elapsed_seconds=total_elapsed,
        )

    # Print per-model summaries
    for model, m in model_metrics.items():
        print()
        print(m.summary())
        print()

    # Write comparison report
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = generate_comparison_report(comparison_results)
    report_path = output_dir / "comparison_report.md"
    report_path.write_text(report)
    print(f"Comparison report written to: {report_path}")

    # Also write individual plan review reports per model
    for model, results in comparison_results.items():
        report = generate_plan_review_report(results, model_metrics[model])
        short_name = model.split("-")[1] if "-" in model else model
        report_path = output_dir / f"plan_review_{short_name}.md"
        report_path.write_text(report)
        print(f"Plan review report ({short_name}) written to: {report_path}")


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    _setup_logging(args.verbose)

    if args.dry_run:
        persona_ids = args.persona or list_persona_ids()
        print("MileMind Evaluation Harness — Dry Run")
        print("=" * 40)
        print(f"Planner model: {args.planner_model}")
        print(f"Reviewer model: {args.reviewer_model}")
        print(f"Compare mode: {args.compare}")
        print(f"Batch mode: {args.batch}")
        print(f"Max retries: {args.max_retries}")
        print(f"Token budget: {args.max_tokens:,}")
        print(f"Output dir: {args.output_dir}")
        print()
        print("Personas to evaluate:")
        for pid in persona_ids:
            persona = next(p for p in ALL_PERSONAS if p.persona_id == pid)
            profile = persona.profile
            print(f"  - {pid}: {profile.name}")
            print(f"    Goal: {profile.goal_distance}, {profile.weekly_mileage_base}km/week base")
            print(f"    Risk: {profile.risk_tolerance.value}")
        return

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    if args.compare:
        asyncio.run(run_comparison(args))
    else:
        asyncio.run(run_single(args))


if __name__ == "__main__":
    main()
