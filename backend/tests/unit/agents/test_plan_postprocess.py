"""Unit tests for plan post-processing (TSS computation)."""

import json

import pytest

from src.agents.plan_postprocess import enrich_plan_with_tss, _compute_workout_tss


class TestComputeWorkoutTss:
    """Tests for _compute_workout_tss helper."""

    def test_easy_run(self) -> None:
        workout = {"workout_type": "easy", "duration_minutes": 50, "intensity": 0.65}
        tss = _compute_workout_tss(workout)
        # TSS = (50*60 * 0.65^2) / 3600 * 100 = 35.21
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
        # TSS = (30*60 * 0.8^2) / 3600 * 100 = 32.0
        assert abs(tss - 32.0) < 0.1


class TestEnrichPlanWithTss:
    """Tests for enrich_plan_with_tss."""

    PLAN_JSON = {
        "athlete_name": "Test Runner",
        "goal_event": "10K",
        "weeks": [
            {
                "week_number": 1,
                "phase": "base",
                "workouts": [
                    {"day": 1, "workout_type": "easy", "duration_minutes": 50, "intensity": 0.65, "description": "Easy run"},
                    {"day": 3, "workout_type": "rest", "description": "Rest day"},
                    {"day": 5, "workout_type": "long_run", "duration_minutes": 60, "intensity": 0.68, "description": "Long run"},
                ],
                "notes": "Base week 1",
            }
        ],
    }

    def _make_plan_text(self, plan_data: dict) -> str:
        """Wrap plan data in markdown code fence."""
        return f"Here is the plan:\n\n```json\n{json.dumps(plan_data, indent=2)}\n```\n\nEnjoy!"

    def test_adds_tss_to_workouts(self) -> None:
        text = self._make_plan_text(self.PLAN_JSON)
        enriched = enrich_plan_with_tss(text)
        assert '"tss"' in enriched
        # Parse back the enriched JSON
        import re
        match = re.search(r"```json\s*\n(.*?)\n\s*```", enriched, re.DOTALL)
        assert match is not None
        data = json.loads(match.group(1))
        workouts = data["weeks"][0]["workouts"]
        assert workouts[0]["tss"] > 0  # easy run has TSS
        assert workouts[1]["tss"] == 0  # rest day
        assert workouts[2]["tss"] > 0  # long run

    def test_adds_target_load(self) -> None:
        text = self._make_plan_text(self.PLAN_JSON)
        enriched = enrich_plan_with_tss(text)
        import re
        match = re.search(r"```json\s*\n(.*?)\n\s*```", enriched, re.DOTALL)
        data = json.loads(match.group(1))
        target_load = data["weeks"][0]["target_load"]
        # Should be sum of workout TSS values
        workout_tss_sum = sum(w["tss"] for w in data["weeks"][0]["workouts"])
        assert abs(target_load - workout_tss_sum) < 0.01

    def test_returns_original_if_no_json_block(self) -> None:
        text = "No JSON here, just plain text."
        assert enrich_plan_with_tss(text) == text

    def test_returns_original_if_invalid_json(self) -> None:
        text = "```json\n{invalid json\n```"
        assert enrich_plan_with_tss(text) == text

    def test_preserves_surrounding_text(self) -> None:
        text = self._make_plan_text(self.PLAN_JSON)
        enriched = enrich_plan_with_tss(text)
        assert enriched.startswith("Here is the plan:")
        assert enriched.endswith("Enjoy!")
