"""Post-process planner output to compute deterministic values.

After the LLM outputs a plan JSON, this module parses it and computes
TSS and target_load values using the deterministic engine. This removes
the need for the LLM to call compute_training_stress for every workout,
significantly reducing token usage.

Usage:
    enriched_text = enrich_plan_with_tss(raw_plan_text)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.deterministic.training_stress import compute_tss

logger = logging.getLogger(__name__)


def _extract_plan_json(plan_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Extract the JSON plan from the planner's text output.

    Looks for a ```json fenced code block and parses it.

    Args:
        plan_text: Raw planner output text.

    Returns:
        Tuple of (parsed dict, raw JSON string) or (None, None) if not found.
    """
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", plan_text, re.DOTALL)
    if not match:
        return None, None
    raw_json = match.group(1)
    try:
        return json.loads(raw_json), raw_json
    except json.JSONDecodeError:
        logger.warning("Failed to parse plan JSON from planner output")
        return None, None


def _compute_workout_tss(workout: dict[str, Any]) -> float:
    """Compute TSS for a single workout using the deterministic engine.

    Args:
        workout: Workout dict with duration_minutes and intensity fields.

    Returns:
        TSS value, or 0.0 for rest days or missing data.
    """
    workout_type = workout.get("workout_type", "")
    if workout_type == "rest":
        return 0.0

    duration = workout.get("duration_minutes", 0)
    intensity = workout.get("intensity", 0)
    if not duration or intensity is None:
        return 0.0
    if intensity == 0:
        return 0.0

    try:
        return round(compute_tss(float(duration), float(intensity)), 2)
    except (ValueError, TypeError):
        return 0.0


def enrich_plan_with_tss(plan_text: str) -> str:
    """Compute TSS and target_load for all workouts in the plan.

    Parses the JSON plan from the planner's output, computes TSS for each
    workout using the deterministic engine, adds target_load to each week,
    and returns the updated plan text with the enriched JSON.

    Args:
        plan_text: Raw planner output containing a ```json block.

    Returns:
        Updated plan text with TSS and target_load values computed.
        Returns original text unchanged if parsing fails.
    """
    plan_data, raw_json = _extract_plan_json(plan_text)
    if plan_data is None or raw_json is None:
        return plan_text

    weeks = plan_data.get("weeks", [])
    if not weeks:
        return plan_text

    total_workouts = 0
    zero_tss_count = 0
    for week in weeks:
        week_tss = 0.0
        for workout in week.get("workouts", []):
            tss = _compute_workout_tss(workout)
            workout["tss"] = tss
            week_tss += tss
            total_workouts += 1
            wtype = workout.get("workout_type", "")
            if tss == 0.0 and wtype != "rest":
                zero_tss_count += 1
        week["target_load"] = round(week_tss, 2)

    if zero_tss_count > 0:
        logger.warning(
            "Post-processing: %d non-rest workout(s) produced TSS=0 "
            "(missing duration or intensity)",
            zero_tss_count,
        )

    logger.info(
        "Post-processed plan: computed TSS for %d workouts across %d weeks",
        total_workouts, len(weeks),
    )

    # Replace the JSON block in the original text
    enriched_json = json.dumps(plan_data, indent=2)
    enriched_text = plan_text.replace(raw_json, enriched_json)
    return enriched_text


def extract_structured_plan(plan_text: str) -> dict[str, Any]:
    """Extract and return the structured plan data from planner output.

    Returns the parsed JSON plan dict (with TSS already computed if
    enrich_plan_with_tss was called first). Falls back to {"text": plan_text}
    if no JSON block is found.

    Args:
        plan_text: Planner output text (should already be enriched with TSS).

    Returns:
        Structured plan dict with weeks, workouts, etc.
    """
    plan_data, _ = _extract_plan_json(plan_text)
    if plan_data is None:
        return {"text": plan_text}
    return plan_data
