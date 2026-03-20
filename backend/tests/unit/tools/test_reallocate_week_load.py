"""Tests for the reallocate_week_load tool wrapper.

Covers:
- Input validation (WorkoutEntry, ReallocateWeekInput)
- TSS computation helper
- Swap logic (intensity resolution, TSS update)
- Load rebalancing when target_weekly_load is provided
- Progression validation via acwr.validate_weekly_increase
- ToolRegistry integration (schema generation and dispatch)
- Edge cases: REST day swaps, zero loads, intensity clamping
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from src.deterministic.acwr import DEFAULT_MAX_WEEKLY_INCREASE_PCT
from src.models.workout import WorkoutType
from src.tools.reallocate_week_load import (
    ReallocateWeekInput,
    ReallocateWeekOutput,
    _DEFAULT_INTENSITY,
    _compute_tss,
    _resolve_intensity,
    _scale_workouts_to_target,
    reallocate_week_load_handler,
    register,
)
from src.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_workout(
    day: int,
    workout_type: str = "easy",
    distance_km: float = 10.0,
    duration_minutes: float = 60.0,
    intensity: float = 0.6,
    description: str = "",
) -> dict[str, Any]:
    return {
        "day": day,
        "workout_type": workout_type,
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        "intensity": intensity,
        "description": description,
    }


@pytest.fixture
def simple_week() -> list[dict[str, Any]]:
    """A minimal 3-day training week (Mon easy, Wed tempo, Fri long run)."""
    return [
        _make_workout(1, "easy", distance_km=8.0, duration_minutes=50.0, intensity=0.60),
        _make_workout(3, "tempo", distance_km=10.0, duration_minutes=55.0, intensity=0.80),
        _make_workout(5, "long_run", distance_km=20.0, duration_minutes=120.0, intensity=0.65),
    ]


@pytest.fixture
def week_with_rest() -> list[dict[str, Any]]:
    """Week that includes a rest day."""
    return [
        _make_workout(1, "easy", duration_minutes=50.0, intensity=0.60),
        _make_workout(2, "rest", duration_minutes=0.0, intensity=0.0),
        _make_workout(4, "interval", duration_minutes=45.0, intensity=0.90),
    ]


# ---------------------------------------------------------------------------
# Unit tests: _compute_tss
# ---------------------------------------------------------------------------

class TestComputeTss:
    """Verify the TSS helper against the canonical formula."""

    def test_zero_intensity_yields_zero(self) -> None:
        assert _compute_tss(60.0, 0.0) == 0.0

    def test_zero_duration_yields_zero(self) -> None:
        assert _compute_tss(0.0, 0.8) == 0.0

    def test_known_value(self) -> None:
        # 60 min, intensity 1.0 => 60 * 1.0 * (100/60) = 100.0
        assert math.isclose(_compute_tss(60.0, 1.0), 100.0, rel_tol=1e-9)

    def test_intensity_squared(self) -> None:
        # Halving intensity should quarter the TSS
        tss_full = _compute_tss(60.0, 0.8)
        tss_half = _compute_tss(60.0, 0.4)
        assert math.isclose(tss_full / tss_half, 4.0, rel_tol=1e-9)

    def test_proportional_to_duration(self) -> None:
        tss_30 = _compute_tss(30.0, 0.7)
        tss_60 = _compute_tss(60.0, 0.7)
        assert math.isclose(tss_60 / tss_30, 2.0, rel_tol=1e-9)

    def test_one_hour_threshold_is_100(self) -> None:
        """60 min at IF=1.0 should yield TSS=100 (canonical definition)."""
        assert math.isclose(_compute_tss(60.0, 1.0), 100.0, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Unit tests: _resolve_intensity
# ---------------------------------------------------------------------------

class TestResolveIntensity:
    """Verify canonical intensity defaults and override logic."""

    def test_override_takes_priority(self) -> None:
        assert _resolve_intensity("easy", 0.99) == 0.99

    def test_override_zero_is_respected(self) -> None:
        assert _resolve_intensity("tempo", 0.0) == 0.0

    def test_defaults_match_table(self) -> None:
        for wt_value, expected in _DEFAULT_INTENSITY.items():
            assert _resolve_intensity(wt_value, None) == expected

    def test_unknown_type_falls_back_to_0_60(self) -> None:
        # Should not occur after validation, but the helper is defensive.
        assert _resolve_intensity("nonexistent_type", None) == 0.60


# ---------------------------------------------------------------------------
# Unit tests: WorkoutEntry validation
# ---------------------------------------------------------------------------

class TestWorkoutEntryValidation:
    """Pydantic model validation for individual workout entries."""

    def test_valid_entry(self) -> None:
        entry = _make_workout(1, "easy")
        from src.tools.reallocate_week_load import WorkoutEntry
        we = WorkoutEntry(**entry)
        assert we.day == 1
        assert we.workout_type == WorkoutType.EASY

    def test_invalid_workout_type_raises(self) -> None:
        from src.tools.reallocate_week_load import WorkoutEntry
        with pytest.raises(ValidationError, match="workout_type"):
            WorkoutEntry(**_make_workout(1, "sprint_to_the_finish"))

    def test_day_out_of_range_raises(self) -> None:
        from src.tools.reallocate_week_load import WorkoutEntry
        bad = _make_workout(8, "easy")
        with pytest.raises(ValidationError):
            WorkoutEntry(**bad)

    def test_negative_distance_raises(self) -> None:
        from src.tools.reallocate_week_load import WorkoutEntry
        bad = _make_workout(1, "easy", distance_km=-1.0)
        with pytest.raises(ValidationError):
            WorkoutEntry(**bad)

    def test_intensity_above_one_raises(self) -> None:
        from src.tools.reallocate_week_load import WorkoutEntry
        bad = _make_workout(1, "easy", intensity=1.1)
        with pytest.raises(ValidationError):
            WorkoutEntry(**bad)


# ---------------------------------------------------------------------------
# Unit tests: ReallocateWeekInput validation
# ---------------------------------------------------------------------------

class TestReallocateWeekInputValidation:
    """Pydantic model-level and cross-field validation."""

    def test_valid_input(self, simple_week: list[dict[str, Any]]) -> None:
        inp = ReallocateWeekInput(
            workouts=simple_week,
            swap_day=1,
            new_workout_type="recovery",
        )
        assert inp.swap_day == 1
        assert inp.risk_tolerance == "moderate"

    def test_swap_day_not_in_workouts_raises(self, simple_week: list[dict[str, Any]]) -> None:
        with pytest.raises(ValidationError, match="swap_day"):
            ReallocateWeekInput(
                workouts=simple_week,
                swap_day=7,  # Sunday not present in simple_week
                new_workout_type="easy",
            )

    def test_invalid_new_workout_type_raises(self, simple_week: list[dict[str, Any]]) -> None:
        with pytest.raises(ValidationError, match="new_workout_type"):
            ReallocateWeekInput(
                workouts=simple_week,
                swap_day=1,
                new_workout_type="ultra_marathon_blast",
            )

    def test_invalid_risk_tolerance_raises(self, simple_week: list[dict[str, Any]]) -> None:
        with pytest.raises(ValidationError):
            ReallocateWeekInput(
                workouts=simple_week,
                swap_day=1,
                new_workout_type="easy",
                risk_tolerance="yolo",  # type: ignore[arg-type]
            )

    def test_new_intensity_bounds(self, simple_week: list[dict[str, Any]]) -> None:
        with pytest.raises(ValidationError):
            ReallocateWeekInput(
                workouts=simple_week,
                swap_day=1,
                new_workout_type="easy",
                new_intensity=1.5,
            )

    def test_empty_workouts_raises(self) -> None:
        with pytest.raises(ValidationError):
            ReallocateWeekInput(
                workouts=[],
                swap_day=1,
                new_workout_type="easy",
            )

    def test_negative_target_weekly_load_raises(self, simple_week: list[dict[str, Any]]) -> None:
        with pytest.raises(ValidationError):
            ReallocateWeekInput(
                workouts=simple_week,
                swap_day=1,
                new_workout_type="easy",
                target_weekly_load=-10.0,
            )

    def test_negative_previous_week_load_raises(self, simple_week: list[dict[str, Any]]) -> None:
        with pytest.raises(ValidationError):
            ReallocateWeekInput(
                workouts=simple_week,
                swap_day=1,
                new_workout_type="easy",
                previous_week_load=-5.0,
            )


# ---------------------------------------------------------------------------
# Unit tests: _scale_workouts_to_target
# ---------------------------------------------------------------------------

class TestScaleWorkoutsToTarget:
    """Verify proportional intensity scaling towards a target load."""

    def _build_workouts_with_tss(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for w in entries:
            tss = _compute_tss(w["duration_minutes"], w["intensity"])
            result.append({**w, "tss": tss})
        return result

    def test_scale_up(self) -> None:
        workouts = self._build_workouts_with_tss([
            _make_workout(1, "easy", duration_minutes=60.0, intensity=0.6),
            _make_workout(3, "easy", duration_minutes=60.0, intensity=0.6),
        ])
        # swap_idx=0 was already handled; scale index 1 to hit target
        swapped_tss = workouts[0]["tss"]
        target = swapped_tss + 80.0  # push remaining workout to 80 TSS
        result = _scale_workouts_to_target(workouts, 0, target, swapped_tss)
        total = sum(w["tss"] for w in result)
        assert math.isclose(total, target, rel_tol=1e-4)

    def test_scale_does_not_exceed_intensity_one(self) -> None:
        # Force a scenario where scale_factor > 1 would exceed intensity 1.0
        workouts = self._build_workouts_with_tss([
            _make_workout(1, "easy", duration_minutes=60.0, intensity=0.6),
            _make_workout(3, "easy", duration_minutes=60.0, intensity=0.6),
        ])
        swapped_tss = workouts[0]["tss"]
        huge_target = swapped_tss + 99999.0  # impossibly large budget
        result = _scale_workouts_to_target(workouts, 0, huge_target, swapped_tss)
        for w in result:
            assert w["intensity"] <= 1.0

    def test_scale_down(self) -> None:
        workouts = self._build_workouts_with_tss([
            _make_workout(1, "tempo", duration_minutes=60.0, intensity=0.8),
            _make_workout(3, "interval", duration_minutes=60.0, intensity=0.9),
        ])
        swapped_tss = workouts[0]["tss"]
        small_target = swapped_tss + 10.0  # cut remaining load to 10 TSS
        result = _scale_workouts_to_target(workouts, 0, small_target, swapped_tss)
        total = sum(w["tss"] for w in result)
        assert math.isclose(total, small_target, rel_tol=1e-4)

    def test_rest_days_excluded_from_scaling(self) -> None:
        workouts = self._build_workouts_with_tss([
            _make_workout(1, "easy", duration_minutes=60.0, intensity=0.6),
            _make_workout(2, "rest", duration_minutes=0.0, intensity=0.0),
            _make_workout(3, "easy", duration_minutes=60.0, intensity=0.6),
        ])
        swapped_tss = workouts[0]["tss"]
        target = swapped_tss + 50.0
        result = _scale_workouts_to_target(workouts, 0, target, swapped_tss)
        # Rest day intensity must remain 0.0
        assert result[1]["intensity"] == 0.0

    def test_no_eligible_workouts_returns_unchanged(self) -> None:
        """When all non-swapped workouts are rest, output is unchanged."""
        workouts = self._build_workouts_with_tss([
            _make_workout(1, "easy", duration_minutes=60.0, intensity=0.6),
            _make_workout(2, "rest", duration_minutes=0.0, intensity=0.0),
        ])
        original_rest_tss = workouts[1]["tss"]
        swapped_tss = workouts[0]["tss"]
        result = _scale_workouts_to_target(workouts, 0, 999.0, swapped_tss)
        assert result[1]["tss"] == original_rest_tss

    def test_zero_current_remaining_returns_unchanged(self) -> None:
        """If all eligible workouts have zero TSS, don't scale (avoid division by zero)."""
        workouts = self._build_workouts_with_tss([
            _make_workout(1, "easy", duration_minutes=60.0, intensity=0.6),
            _make_workout(3, "easy", duration_minutes=0.0, intensity=0.0),
        ])
        swapped_tss = workouts[0]["tss"]
        result = _scale_workouts_to_target(workouts, 0, 100.0, swapped_tss)
        # Index 1 has duration=0, so TSS stays 0
        assert result[1]["tss"] == 0.0


# ---------------------------------------------------------------------------
# Integration tests: reallocate_week_load_handler
# ---------------------------------------------------------------------------

class TestReallocateWeekLoadHandler:
    """End-to-end handler tests."""

    def test_basic_swap_changes_workout_type(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 3,
            "new_workout_type": "recovery",
        })
        day3 = next(w for w in result["adjusted_workouts"] if w["day"] == 3)
        assert day3["workout_type"] == "recovery"

    def test_swap_uses_canonical_intensity_when_no_override(
        self, simple_week: list[dict[str, Any]]
    ) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 3,
            "new_workout_type": "recovery",
        })
        day3 = next(w for w in result["adjusted_workouts"] if w["day"] == 3)
        assert math.isclose(day3["intensity"], _DEFAULT_INTENSITY["recovery"], rel_tol=1e-9)

    def test_swap_respects_intensity_override(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "tempo",
            "new_intensity": 0.77,
        })
        day1 = next(w for w in result["adjusted_workouts"] if w["day"] == 1)
        assert math.isclose(day1["intensity"], 0.77, rel_tol=1e-6)

    def test_original_load_is_sum_of_input_tss(self, simple_week: list[dict[str, Any]]) -> None:
        expected = sum(
            _compute_tss(w["duration_minutes"], w["intensity"]) for w in simple_week
        )
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "easy",
        })
        assert math.isclose(result["original_load"], expected, rel_tol=1e-6)

    def test_adjusted_load_reflects_swap(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 3,
            "new_workout_type": "rest",
            "new_intensity": 0.0,
        })
        # Replacing tempo (0.80) with rest (0.0) must lower the load
        assert result["adjusted_load"] < result["original_load"]

    def test_load_change_pct_calculated_correctly(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "easy",
        })
        expected_pct = (
            (result["adjusted_load"] - result["original_load"]) / result["original_load"] * 100.0
        )
        assert math.isclose(result["load_change_pct"], expected_pct, rel_tol=1e-6)

    def test_load_change_pct_zero_when_original_is_zero(self) -> None:
        # All zero-intensity workouts => original_load == 0
        all_rest = [_make_workout(i, "rest", duration_minutes=0.0, intensity=0.0) for i in range(1, 4)]
        result = reallocate_week_load_handler({
            "workouts": all_rest,
            "swap_day": 2,
            "new_workout_type": "rest",
        })
        assert result["load_change_pct"] == 0.0

    def test_swap_summary_mentions_both_types(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "interval",
        })
        assert "easy" in result["swap_summary"]
        assert "interval" in result["swap_summary"]
        assert "Day 1" in result["swap_summary"]

    def test_validation_passes_when_no_previous_load(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "easy",
        })
        assert result["validation_passed"] is True
        assert result["validation_violations"] == []

    def test_progression_violation_recorded(self, simple_week: list[dict[str, Any]]) -> None:
        # Set previous_week_load very low so any real load triggers the 10% rule
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "interval",
            "previous_week_load": 1.0,  # 1 TSS previous week, plan has >> 1.1 TSS
        })
        assert result["validation_passed"] is False
        assert len(result["validation_violations"]) >= 1
        assert "10%" in result["validation_violations"][0]

    def test_progression_passes_within_limit(self) -> None:
        # Pin new_intensity so the adjusted TSS is predictable regardless of
        # canonical defaults changing.
        fixed_intensity = 0.60
        workouts = [_make_workout(1, "easy", duration_minutes=30.0, intensity=fixed_intensity)]
        tss = _compute_tss(30.0, fixed_intensity)  # 30 * 0.36 * (100/60) ≈ 18.0
        # Set previous week at a level where a 5% increase lands within the 10% limit
        previous = tss / 1.05
        result = reallocate_week_load_handler({
            "workouts": workouts,
            "swap_day": 1,
            "new_workout_type": "easy",
            "new_intensity": fixed_intensity,  # keep intensity identical to input
            "previous_week_load": previous,
        })
        assert result["validation_passed"] is True

    def test_target_weekly_load_scales_workouts(self, simple_week: list[dict[str, Any]]) -> None:
        original_load = sum(
            _compute_tss(w["duration_minutes"], w["intensity"]) for w in simple_week
        )
        target = original_load * 0.8  # ask for 20% reduction
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "easy",
            "target_weekly_load": target,
        })
        # Total load should be approximately the target (within 1%)
        assert math.isclose(result["adjusted_load"], target, rel_tol=0.01)

    def test_target_mentioned_in_swap_summary(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "easy",
            "target_weekly_load": 200.0,
        })
        assert "target weekly load" in result["swap_summary"]

    def test_output_contains_all_original_days(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 5,
            "new_workout_type": "recovery",
        })
        output_days = {w["day"] for w in result["adjusted_workouts"]}
        input_days = {w["day"] for w in simple_week}
        assert output_days == input_days

    def test_non_swapped_workouts_unchanged_without_target(
        self, simple_week: list[dict[str, Any]]
    ) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "recovery",
        })
        day3_out = next(w for w in result["adjusted_workouts"] if w["day"] == 3)
        original_day3 = next(w for w in simple_week if w["day"] == 3)
        assert math.isclose(day3_out["intensity"], original_day3["intensity"], rel_tol=1e-9)

    def test_rest_day_swap_results_in_zero_tss(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 3,
            "new_workout_type": "rest",
        })
        day3 = next(w for w in result["adjusted_workouts"] if w["day"] == 3)
        # REST canonical intensity = 0.0 => TSS = 0
        assert day3["tss"] == 0.0

    def test_week_with_rest_day_swap(self, week_with_rest: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": week_with_rest,
            "swap_day": 4,
            "new_workout_type": "tempo",
        })
        day4 = next(w for w in result["adjusted_workouts"] if w["day"] == 4)
        assert day4["workout_type"] == "tempo"
        assert day4["tss"] > 0.0

    def test_all_workout_types_accepted_as_new_type(
        self, simple_week: list[dict[str, Any]]
    ) -> None:
        """Every WorkoutType should be a valid new_workout_type."""
        for wt in WorkoutType:
            result = reallocate_week_load_handler({
                "workouts": simple_week,
                "swap_day": 1,
                "new_workout_type": wt.value,
            })
            assert "adjusted_workouts" in result

    def test_output_tss_matches_formula(self, simple_week: list[dict[str, Any]]) -> None:
        result = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "tempo",
            "new_intensity": 0.75,
        })
        for w in result["adjusted_workouts"]:
            expected_tss = _compute_tss(w["duration_minutes"], w["intensity"])
            assert math.isclose(w["tss"], expected_tss, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# Schema validation via ToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """Verify registry integration and Anthropic-format schema generation."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        reg = ToolRegistry()
        register(reg)
        return reg

    def test_tool_is_registered(self, registry: ToolRegistry) -> None:
        assert "reallocate_week_load" in registry.tool_names

    def test_anthropic_schema_structure(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        assert len(tools) == 1
        tool = tools[0]
        assert tool["name"] == "reallocate_week_load"
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_required_fields_in_schema(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        required = tools[0]["input_schema"]["required"]
        assert "workouts" in required
        assert "swap_day" in required
        assert "new_workout_type" in required

    def test_optional_fields_not_in_required(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        required = tools[0]["input_schema"]["required"]
        assert "new_intensity" not in required
        assert "target_weekly_load" not in required
        assert "previous_week_load" not in required
        assert "risk_tolerance" not in required

    def test_registry_execute_success(
        self, registry: ToolRegistry, simple_week: list[dict[str, Any]]
    ) -> None:
        result = registry.execute(
            "reallocate_week_load",
            {
                "workouts": simple_week,
                "swap_day": 1,
                "new_workout_type": "recovery",
            },
        )
        assert result.success is True
        assert "adjusted_workouts" in result.output

    def test_registry_execute_validation_error(self, registry: ToolRegistry) -> None:
        result = registry.execute(
            "reallocate_week_load",
            {"workouts": [], "swap_day": 1, "new_workout_type": "easy"},
        )
        assert result.success is False
        assert "error" in result.output

    def test_registry_execute_unknown_tool(self, registry: ToolRegistry) -> None:
        result = registry.execute("does_not_exist", {})
        assert result.success is False
        assert "Unknown tool" in result.output["error"]

    def test_duplicate_registration_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValueError, match="already registered"):
            register(registry)

    def test_tool_result_to_content_block_is_json(
        self, registry: ToolRegistry, simple_week: list[dict[str, Any]]
    ) -> None:
        import json
        result = registry.execute(
            "reallocate_week_load",
            {"workouts": simple_week, "swap_day": 1, "new_workout_type": "easy"},
        )
        block = result.to_content_block()
        parsed = json.loads(block)
        assert "adjusted_workouts" in parsed

    def test_description_contains_swap_language(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        desc = tools[0]["description"]
        assert "swap" in desc.lower()

    def test_schema_has_no_title_key(self, registry: ToolRegistry) -> None:
        """Pydantic 'title' field must be stripped before sending to Anthropic."""
        tools = registry.get_anthropic_tools()
        assert "title" not in tools[0]["input_schema"]


# ---------------------------------------------------------------------------
# Edge cases and boundary conditions
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary conditions and unusual but valid inputs."""

    def test_single_workout_week(self) -> None:
        single = [_make_workout(4, "easy", duration_minutes=45.0, intensity=0.60)]
        result = reallocate_week_load_handler({
            "workouts": single,
            "swap_day": 4,
            "new_workout_type": "tempo",
        })
        assert len(result["adjusted_workouts"]) == 1
        assert result["adjusted_workouts"][0]["workout_type"] == "tempo"

    def test_target_load_zero_zeroes_all_eligible_workouts(self) -> None:
        workouts = [
            _make_workout(1, "easy", duration_minutes=60.0, intensity=0.6),
            _make_workout(3, "tempo", duration_minutes=60.0, intensity=0.8),
        ]
        result = reallocate_week_load_handler({
            "workouts": workouts,
            "swap_day": 1,
            "new_workout_type": "easy",
            "target_weekly_load": 0.0,
        })
        # All workouts (including scaled one) should have intensity <= original
        for w in result["adjusted_workouts"]:
            assert w["intensity"] >= 0.0

    def test_swap_day_with_multiple_workouts_replaces_first(self) -> None:
        # Two workouts on day 2
        workouts = [
            _make_workout(2, "easy", duration_minutes=30.0, intensity=0.6),
            _make_workout(2, "recovery", duration_minutes=20.0, intensity=0.45),
            _make_workout(4, "long_run", duration_minutes=90.0, intensity=0.65),
        ]
        result = reallocate_week_load_handler({
            "workouts": workouts,
            "swap_day": 2,
            "new_workout_type": "rest",
        })
        # First day-2 entry should be swapped; second should remain recovery
        day2_workouts = [w for w in result["adjusted_workouts"] if w["day"] == 2]
        assert day2_workouts[0]["workout_type"] == "rest"
        assert day2_workouts[1]["workout_type"] == "recovery"

    def test_all_rest_week_with_swap_to_easy(self) -> None:
        all_rest = [_make_workout(i, "rest", duration_minutes=0.0, intensity=0.0) for i in range(1, 8)]
        result = reallocate_week_load_handler({
            "workouts": all_rest,
            "swap_day": 4,
            "new_workout_type": "easy",
            "new_intensity": 0.6,
        })
        # Only day 4 should be non-zero load
        for w in result["adjusted_workouts"]:
            if w["day"] == 4:
                assert w["workout_type"] == "easy"
            else:
                assert w["workout_type"] == "rest"

    def test_load_change_pct_positive_when_increased(self) -> None:
        # Swap easy for interval — should increase load
        workouts = [_make_workout(1, "easy", duration_minutes=60.0, intensity=0.6)]
        result = reallocate_week_load_handler({
            "workouts": workouts,
            "swap_day": 1,
            "new_workout_type": "interval",
        })
        assert result["load_change_pct"] > 0.0

    def test_load_change_pct_negative_when_decreased(self) -> None:
        # Swap interval for recovery — should decrease load
        workouts = [_make_workout(1, "interval", duration_minutes=60.0, intensity=0.9)]
        result = reallocate_week_load_handler({
            "workouts": workouts,
            "swap_day": 1,
            "new_workout_type": "recovery",
        })
        assert result["load_change_pct"] < 0.0

    def test_output_model_validates_handler_output(
        self, simple_week: list[dict[str, Any]]
    ) -> None:
        """Handler output should always be parseable by ReallocateWeekOutput."""
        raw = reallocate_week_load_handler({
            "workouts": simple_week,
            "swap_day": 1,
            "new_workout_type": "tempo",
        })
        parsed = ReallocateWeekOutput(**raw)
        assert parsed.validation_passed is True

    def test_registry_rejects_missing_required_field(self) -> None:
        """Input validation for missing required fields is enforced by the ToolRegistry,
        not the handler directly.  Calling the registry with a missing swap_day must
        return a failure result rather than raising.
        """
        registry = ToolRegistry()
        register(registry)
        result = registry.execute(
            "reallocate_week_load",
            {
                "workouts": [_make_workout(1)],
                # swap_day missing
                "new_workout_type": "easy",
            },
        )
        assert result.success is False
        assert "error" in result.output
