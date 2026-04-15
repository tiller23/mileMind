"""Unit tests for plan post-processing (TSS computation and structured extraction)."""

import json
import re

from src.agents.plan_postprocess import (
    _compute_workout_tss,
    enrich_plan_with_tss,
    extract_structured_plan,
)

SAMPLE_PLAN = {
    "athlete_name": "Test Runner",
    "goal_event": "10K",
    "weeks": [
        {
            "week_number": 1,
            "phase": "base",
            "workouts": [
                {
                    "day": 1,
                    "workout_type": "easy",
                    "duration_minutes": 50,
                    "intensity": 0.65,
                    "description": "Easy run",
                },
                {"day": 3, "workout_type": "rest", "description": "Rest day"},
                {
                    "day": 5,
                    "workout_type": "long_run",
                    "duration_minutes": 60,
                    "intensity": 0.68,
                    "description": "Long run",
                },
            ],
            "notes": "Base week 1",
        }
    ],
}


def _make_plan_text(plan_data: dict) -> str:
    """Wrap plan data in markdown code fence."""
    return f"Here is the plan:\n\n```json\n{json.dumps(plan_data, indent=2)}\n```\n\nEnjoy!"


class TestComputeWorkoutTss:
    """Tests for _compute_workout_tss helper."""

    def test_easy_run(self) -> None:
        workout = {"workout_type": "easy", "duration_minutes": 50, "intensity": 0.65}
        tss = _compute_workout_tss(workout)
        assert abs(tss - 35.21) < 0.1

    def test_rest_day_returns_zero(self) -> None:
        workout = {"workout_type": "rest"}
        assert _compute_workout_tss(workout) == 0.0

    def test_missing_duration_returns_zero(self) -> None:
        workout = {"workout_type": "easy", "intensity": 0.65}
        assert _compute_workout_tss(workout) == 0.0

    def test_missing_intensity_returns_zero(self) -> None:
        workout = {"workout_type": "easy", "duration_minutes": 50}
        assert _compute_workout_tss(workout) == 0.0

    def test_tempo_run(self) -> None:
        workout = {"workout_type": "tempo", "duration_minutes": 30, "intensity": 0.80}
        tss = _compute_workout_tss(workout)
        assert abs(tss - 32.0) < 0.1


class TestEnrichPlanWithTss:
    """Tests for enrich_plan_with_tss."""

    def test_adds_tss_to_workouts(self) -> None:
        text = _make_plan_text(SAMPLE_PLAN)
        enriched = enrich_plan_with_tss(text)
        assert '"tss"' in enriched
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", enriched, re.DOTALL)
        assert match is not None
        data = json.loads(match.group(1))
        workouts = data["weeks"][0]["workouts"]
        assert workouts[0]["tss"] > 0
        assert workouts[1]["tss"] == 0
        assert workouts[2]["tss"] > 0

    def test_adds_target_load(self) -> None:
        text = _make_plan_text(SAMPLE_PLAN)
        enriched = enrich_plan_with_tss(text)
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", enriched, re.DOTALL)
        data = json.loads(match.group(1))
        target_load = data["weeks"][0]["target_load"]
        workout_tss_sum = sum(w["tss"] for w in data["weeks"][0]["workouts"])
        assert abs(target_load - workout_tss_sum) < 0.01

    def test_returns_original_if_no_json_block(self) -> None:
        text = "No JSON here, just plain text."
        assert enrich_plan_with_tss(text) == text

    def test_returns_original_if_invalid_json(self) -> None:
        text = "```json\n{invalid json\n```"
        assert enrich_plan_with_tss(text) == text

    def test_preserves_surrounding_text(self) -> None:
        text = _make_plan_text(SAMPLE_PLAN)
        enriched = enrich_plan_with_tss(text)
        assert enriched.startswith("Here is the plan:")
        assert enriched.endswith("Enjoy!")


class TestExtractStructuredPlan:
    """Tests for extract_structured_plan."""

    def test_extracts_structured_data(self) -> None:
        text = _make_plan_text(SAMPLE_PLAN)
        result = extract_structured_plan(text)
        assert "weeks" in result
        assert result["athlete_name"] == "Test Runner"
        assert result["goal_event"] == "10K"
        assert len(result["weeks"]) == 1

    def test_fallback_when_no_json_block(self) -> None:
        text = "Just plain text, no JSON."
        result = extract_structured_plan(text)
        assert result == {"text": "Just plain text, no JSON."}

    def test_fallback_when_malformed_json(self) -> None:
        text = "```json\n{not valid\n```"
        result = extract_structured_plan(text)
        assert result == {"text": text}

    def test_does_not_include_raw_text(self) -> None:
        """Structured plan should not include raw LLM output."""
        text = _make_plan_text(SAMPLE_PLAN)
        result = extract_structured_plan(text)
        assert "_raw_text" not in result

    def test_handles_code_fence_without_json_tag(self) -> None:
        """Should parse code fences without the 'json' language tag."""
        text = f"Plan:\n\n```\n{json.dumps(SAMPLE_PLAN)}\n```"
        result = extract_structured_plan(text)
        assert "weeks" in result

    def test_multiple_code_blocks_uses_first(self) -> None:
        """When multiple code blocks exist, use the first one."""
        plan2 = {"other": "data"}
        text = f"```json\n{json.dumps(SAMPLE_PLAN)}\n```\n\n```json\n{json.dumps(plan2)}\n```"
        result = extract_structured_plan(text)
        assert "weeks" in result
        assert "other" not in result
