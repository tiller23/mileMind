"""Tests for the compute_training_stress tool wrapper.

Validates:
- Pydantic input/output schema compliance
- TSS formula correctness
- HR-based intensity factor derivation
- Load classification thresholds
- Edge cases and boundary values
- ToolRegistry integration (schema generation, dispatch, error handling)
- REST workout clamping behaviour

All physiological arithmetic is deterministic; tests use exact expected values
derived from the formula TSS = (duration_seconds * IF^2) / 3600 * 100.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.deterministic.training_stress import (
    _TSS_EASY_UPPER as _EASY_CEILING,
)
from src.deterministic.training_stress import (
    _TSS_HARD_UPPER as _HARD_CEILING,
)
from src.deterministic.training_stress import (
    _TSS_MODERATE_UPPER as _MODERATE_CEILING,
)
from src.deterministic.training_stress import (
    DEFAULT_THRESHOLD_HR as _DEFAULT_THRESHOLD_HR,
)
from src.models.workout import WorkoutType
from src.tools.compute_training_stress import (
    ComputeTrainingStressInput,
    ComputeTrainingStressOutput,
    _classify_load,
    _compute_tss,
    _resolve_intensity_factor,
    compute_training_stress_handler,
    register,
)
from src.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(**overrides) -> dict:
    """Return a minimal valid input dict, with optional overrides."""
    base = {
        "workout_type": "easy",
        "duration_minutes": 60.0,
        "intensity": 0.65,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ComputeTrainingStressInput validation
# ---------------------------------------------------------------------------


class TestComputeTrainingStressInput:
    """Schema validation for the Pydantic input model."""

    def test_valid_minimal_input(self) -> None:
        """Minimal required fields should parse without error."""
        data = ComputeTrainingStressInput(
            workout_type=WorkoutType.EASY,
            duration_minutes=45.0,
            intensity=0.60,
        )
        assert data.workout_type == WorkoutType.EASY
        assert data.duration_minutes == 45.0
        assert data.intensity == 0.60
        assert data.distance_km is None
        assert data.avg_heart_rate is None

    def test_valid_full_input(self) -> None:
        """All fields accepted when within valid ranges."""
        data = ComputeTrainingStressInput(
            workout_type=WorkoutType.TEMPO,
            duration_minutes=50.0,
            intensity=0.85,
            distance_km=12.0,
            avg_heart_rate=162,
        )
        assert data.distance_km == 12.0
        assert data.avg_heart_rate == 162

    def test_all_workout_types_accepted(self) -> None:
        """Every WorkoutType value should be a valid input."""
        for wt in WorkoutType:
            data = ComputeTrainingStressInput(
                workout_type=wt,
                duration_minutes=30.0,
                intensity=0.0 if wt == WorkoutType.REST else 0.5,
            )
            assert data.workout_type == wt

    def test_workout_type_as_string(self) -> None:
        """WorkoutType should accept raw string values (LLM sends strings)."""
        data = ComputeTrainingStressInput(**_make_input(workout_type="tempo"))
        assert data.workout_type == WorkoutType.TEMPO

    # --- duration_minutes ---

    def test_duration_must_be_positive(self) -> None:
        """duration_minutes <= 0 must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(duration_minutes=0.0))

    def test_duration_negative_raises(self) -> None:
        """Negative duration must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(duration_minutes=-10.0))

    def test_duration_very_small_positive_ok(self) -> None:
        """A very small positive duration is valid."""
        data = ComputeTrainingStressInput(**_make_input(duration_minutes=0.001))
        assert data.duration_minutes == pytest.approx(0.001)

    # --- intensity ---

    def test_intensity_zero_valid(self) -> None:
        """Intensity of exactly 0.0 is valid."""
        data = ComputeTrainingStressInput(**_make_input(intensity=0.0))
        assert data.intensity == 0.0

    def test_intensity_one_valid(self) -> None:
        """Intensity of exactly 1.0 is valid."""
        data = ComputeTrainingStressInput(**_make_input(intensity=1.0))
        assert data.intensity == 1.0

    def test_intensity_above_one_raises(self) -> None:
        """Intensity > 1.0 must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(intensity=1.01))

    def test_intensity_below_zero_raises(self) -> None:
        """Intensity < 0.0 must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(intensity=-0.01))

    # --- distance_km ---

    def test_distance_km_optional(self) -> None:
        """distance_km is not required."""
        data = ComputeTrainingStressInput(**_make_input())
        assert data.distance_km is None

    def test_distance_km_zero_raises(self) -> None:
        """distance_km of 0 must raise ValidationError (gt=0)."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(distance_km=0.0))

    def test_distance_km_negative_raises(self) -> None:
        """Negative distance must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(distance_km=-5.0))

    def test_distance_km_positive_ok(self) -> None:
        """Valid positive distance is accepted."""
        data = ComputeTrainingStressInput(**_make_input(distance_km=10.5))
        assert data.distance_km == 10.5

    # --- avg_heart_rate ---

    def test_avg_heart_rate_optional(self) -> None:
        """avg_heart_rate is not required."""
        data = ComputeTrainingStressInput(**_make_input())
        assert data.avg_heart_rate is None

    def test_avg_heart_rate_lower_bound(self) -> None:
        """HR of 60 bpm is the minimum accepted value."""
        data = ComputeTrainingStressInput(**_make_input(avg_heart_rate=60))
        assert data.avg_heart_rate == 60

    def test_avg_heart_rate_upper_bound(self) -> None:
        """HR of 250 bpm is the maximum accepted value."""
        data = ComputeTrainingStressInput(**_make_input(avg_heart_rate=250))
        assert data.avg_heart_rate == 250

    def test_avg_heart_rate_below_minimum_raises(self) -> None:
        """HR below 60 bpm must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(avg_heart_rate=59))

    def test_avg_heart_rate_above_maximum_raises(self) -> None:
        """HR above 250 bpm must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressInput(**_make_input(avg_heart_rate=251))

    # --- REST workout clamping ---

    def test_rest_workout_clamps_intensity_to_zero(self) -> None:
        """REST workout type forces intensity to 0.0 regardless of input."""
        data = ComputeTrainingStressInput(
            workout_type=WorkoutType.REST,
            duration_minutes=30.0,
            intensity=0.5,  # non-zero, should be clamped
        )
        assert data.intensity == 0.0

    def test_rest_workout_zero_intensity_unchanged(self) -> None:
        """REST workout with intensity already 0 is fine."""
        data = ComputeTrainingStressInput(
            workout_type=WorkoutType.REST,
            duration_minutes=30.0,
            intensity=0.0,
        )
        assert data.intensity == 0.0


# ---------------------------------------------------------------------------
# ComputeTrainingStressOutput validation
# ---------------------------------------------------------------------------


class TestComputeTrainingStressOutput:
    """Schema validation for the Pydantic output model."""

    def test_valid_output(self) -> None:
        """Valid output fields should parse without error."""
        out = ComputeTrainingStressOutput(
            tss=75.0,
            load_classification="moderate",
            intensity_factor=0.85,
            duration_hours=1.0,
        )
        assert out.tss == 75.0
        assert out.load_classification == "moderate"

    def test_tss_must_be_non_negative(self) -> None:
        """TSS < 0 must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressOutput(
                tss=-1.0,
                load_classification="easy",
                intensity_factor=0.5,
                duration_hours=1.0,
            )

    def test_invalid_load_classification_raises(self) -> None:
        """An unrecognised classification label must raise ValidationError."""
        with pytest.raises(ValidationError):
            ComputeTrainingStressOutput(
                tss=60.0,
                load_classification="extreme",  # not in Literal
                intensity_factor=0.5,
                duration_hours=1.0,
            )

    def test_all_valid_classifications(self) -> None:
        """All four classification labels are valid."""
        for label in ("easy", "moderate", "hard", "very_hard"):
            out = ComputeTrainingStressOutput(
                tss=0.0,
                load_classification=label,
                intensity_factor=0.0,
                duration_hours=1.0,
            )
            assert out.load_classification == label


# ---------------------------------------------------------------------------
# Internal pure functions
# ---------------------------------------------------------------------------


class TestResolvIntensityFactor:
    """Unit tests for _resolve_intensity_factor."""

    def test_no_hr_returns_intensity_directly(self) -> None:
        """Without avg_heart_rate, intensity is returned unchanged."""
        assert _resolve_intensity_factor(0.75, None) == pytest.approx(0.75)

    def test_with_hr_uses_threshold_ratio(self) -> None:
        """With HR, IF = avg_hr / _DEFAULT_THRESHOLD_HR."""
        hr = 140
        expected = hr / _DEFAULT_THRESHOLD_HR
        result = _resolve_intensity_factor(0.99, hr)
        assert result == pytest.approx(expected)

    def test_hr_above_threshold_clamped_to_one(self) -> None:
        """HR exceeding threshold HR yields IF clamped to 1.0."""
        hr = _DEFAULT_THRESHOLD_HR + 50  # 225 bpm — way above threshold
        result = _resolve_intensity_factor(0.5, hr)
        assert result == pytest.approx(1.0)

    def test_hr_at_threshold_gives_if_one(self) -> None:
        """HR exactly at threshold yields IF = 1.0."""
        result = _resolve_intensity_factor(0.5, _DEFAULT_THRESHOLD_HR)
        assert result == pytest.approx(1.0)

    def test_hr_at_zero_gives_if_zero(self) -> None:
        """HR / threshold = 0 / 175 = 0.0 — although physically unrealistic."""
        # The pydantic model prevents HR < 30, but the helper has no such guard
        result = _resolve_intensity_factor(0.5, 0)
        assert result == pytest.approx(0.0)

    def test_intensity_zero_no_hr_returns_zero(self) -> None:
        """Zero intensity with no HR should return 0.0."""
        assert _resolve_intensity_factor(0.0, None) == pytest.approx(0.0)


class TestClassifyLoad:
    """Unit tests for _classify_load."""

    @pytest.mark.parametrize(
        "tss,expected",
        [
            (0.0, "easy"),
            (49.99, "easy"),
            (_EASY_CEILING - 0.001, "easy"),
            (_EASY_CEILING, "moderate"),
            (75.0, "moderate"),
            (_MODERATE_CEILING - 0.001, "moderate"),
            (_MODERATE_CEILING, "hard"),
            (150.0, "hard"),
            (_HARD_CEILING - 0.001, "hard"),
            (_HARD_CEILING, "very_hard"),
            (300.0, "very_hard"),
            (1000.0, "very_hard"),
        ],
    )
    def test_classification_boundary(self, tss: float, expected: str) -> None:
        """Each TSS value should map to the correct classification."""
        assert _classify_load(tss) == expected


class TestComputeTSS:
    """Unit tests for the core TSS formula."""

    def test_one_hour_at_threshold_is_100_tss(self) -> None:
        """By definition, 60 min at IF=1.0 should yield TSS=100."""
        tss = _compute_tss(duration_minutes=60.0, intensity_factor=1.0)
        assert tss == pytest.approx(100.0, rel=1e-10)

    def test_two_hours_at_threshold_is_200_tss(self) -> None:
        """Two hours at IF=1.0 should yield TSS=200."""
        tss = _compute_tss(duration_minutes=120.0, intensity_factor=1.0)
        assert tss == pytest.approx(200.0, rel=1e-10)

    def test_zero_intensity_gives_zero_tss(self) -> None:
        """IF=0 must yield TSS=0 regardless of duration."""
        tss = _compute_tss(duration_minutes=90.0, intensity_factor=0.0)
        assert tss == pytest.approx(0.0)

    def test_tss_scales_quadratically_with_if(self) -> None:
        """Doubling IF should quadruple TSS (for the same duration)."""
        tss_low = _compute_tss(60.0, 0.5)
        tss_high = _compute_tss(60.0, 1.0)
        assert tss_high == pytest.approx(4 * tss_low, rel=1e-10)

    def test_tss_scales_linearly_with_duration(self) -> None:
        """Doubling duration should double TSS (for the same IF)."""
        tss_short = _compute_tss(30.0, 0.75)
        tss_long = _compute_tss(60.0, 0.75)
        assert tss_long == pytest.approx(2 * tss_short, rel=1e-10)

    @pytest.mark.parametrize(
        "minutes,intensity,expected_tss",
        [
            (30.0, 0.60, 18.0),  # 30 min easy: (1800 * 0.36) / 3600 * 100 = 18
            (60.0, 0.75, 56.25),  # 60 min tempo-ish: (3600 * 0.5625) / 3600 * 100 = 56.25
            (90.0, 0.85, 108.375),  # 90 min hard: (5400 * 0.7225) / 3600 * 100 = 108.375
            (45.0, 1.0, 75.0),  # 45 min at threshold: (2700 * 1.0) / 3600 * 100 = 75
        ],
    )
    def test_tss_formula_known_values(
        self, minutes: float, intensity: float, expected_tss: float
    ) -> None:
        """Spot-check computed TSS against hand-calculated values."""
        tss = _compute_tss(minutes, intensity)
        assert tss == pytest.approx(expected_tss, rel=1e-8)


# ---------------------------------------------------------------------------
# Handler integration
# ---------------------------------------------------------------------------


class TestComputeTrainingStressHandler:
    """Integration tests for compute_training_stress_handler."""

    def test_returns_dict(self) -> None:
        """Handler must return a plain dict."""
        result = compute_training_stress_handler(_make_input())
        assert isinstance(result, dict)

    def test_output_keys_match_schema(self) -> None:
        """Returned dict must contain exactly the fields in ComputeTrainingStressOutput."""
        result = compute_training_stress_handler(_make_input())
        expected_keys = {"tss", "load_classification", "intensity_factor", "duration_hours"}
        assert set(result.keys()) == expected_keys

    def test_tss_is_non_negative(self) -> None:
        """TSS in handler output must be >= 0."""
        result = compute_training_stress_handler(_make_input(intensity=0.0))
        assert result["tss"] >= 0.0

    def test_duration_hours_correct(self) -> None:
        """duration_hours must equal duration_minutes / 60."""
        result = compute_training_stress_handler(_make_input(duration_minutes=90.0))
        assert result["duration_hours"] == pytest.approx(1.5)

    def test_intensity_factor_without_hr(self) -> None:
        """Without avg_heart_rate, intensity_factor should equal the input intensity."""
        result = compute_training_stress_handler(_make_input(intensity=0.7))
        assert result["intensity_factor"] == pytest.approx(0.7)

    def test_intensity_factor_with_hr_overrides_intensity(self) -> None:
        """With avg_heart_rate, intensity_factor should be HR-derived, not intensity."""
        hr = 140
        result = compute_training_stress_handler(_make_input(intensity=0.99, avg_heart_rate=hr))
        expected_if = hr / _DEFAULT_THRESHOLD_HR
        assert result["intensity_factor"] == pytest.approx(expected_if)

    def test_load_classification_easy(self) -> None:
        """Short easy effort should classify as 'easy'."""
        result = compute_training_stress_handler(
            _make_input(duration_minutes=20.0, intensity=0.50)
        )
        assert result["load_classification"] == "easy"

    def test_load_classification_very_hard(self) -> None:
        """Long hard effort should classify as 'very_hard'."""
        result = compute_training_stress_handler(
            _make_input(duration_minutes=150.0, intensity=1.0)
        )
        assert result["load_classification"] == "very_hard"

    def test_rest_workout_yields_zero_tss(self) -> None:
        """REST workout type must produce TSS=0 regardless of other inputs."""
        result = compute_training_stress_handler(_make_input(workout_type="rest", intensity=0.8))
        assert result["tss"] == pytest.approx(0.0)

    def test_output_passes_pydantic_validation(self) -> None:
        """Handler output should be parseable by ComputeTrainingStressOutput."""
        result = compute_training_stress_handler(_make_input())
        out = ComputeTrainingStressOutput(**result)  # raises if invalid
        assert out.tss >= 0.0

    def test_all_workout_types_handled(self) -> None:
        """Every WorkoutType should produce a valid result without raising."""
        for wt in WorkoutType:
            intensity = 0.0 if wt == WorkoutType.REST else 0.6
            result = compute_training_stress_handler(
                _make_input(workout_type=wt.value, intensity=intensity)
            )
            assert result["tss"] >= 0.0

    @pytest.mark.parametrize(
        "duration,intensity,expected_tss",
        [
            (60.0, 1.0, 100.0),
            (120.0, 1.0, 200.0),
            (30.0, 0.6, 18.0),
        ],
    )
    def test_handler_formula_correctness(
        self, duration: float, intensity: float, expected_tss: float
    ) -> None:
        """Handler TSS values must match the closed-form formula."""
        result = compute_training_stress_handler(
            _make_input(duration_minutes=duration, intensity=intensity)
        )
        assert result["tss"] == pytest.approx(expected_tss, rel=1e-8)


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for tool registration and ToolRegistry dispatch."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """Fresh ToolRegistry with the tool registered."""
        r = ToolRegistry()
        register(r)
        return r

    def test_tool_is_registered(self, registry: ToolRegistry) -> None:
        """compute_training_stress should appear in registered tool names."""
        assert "compute_training_stress" in registry.tool_names

    def test_anthropic_schema_structure(self, registry: ToolRegistry) -> None:
        """Anthropic-format tool definition should have name, description, input_schema."""
        tools = registry.get_anthropic_tools()
        assert len(tools) == 1
        tool_def = tools[0]
        assert tool_def["name"] == "compute_training_stress"
        assert "description" in tool_def
        assert "input_schema" in tool_def

    def test_schema_has_required_properties(self, registry: ToolRegistry) -> None:
        """JSON schema must declare workout_type, duration_minutes, intensity as required."""
        tools = registry.get_anthropic_tools()
        schema = tools[0]["input_schema"]
        required = schema.get("required", [])
        for field in ("workout_type", "duration_minutes", "intensity"):
            assert field in required, f"'{field}' missing from required fields"

    def test_schema_has_optional_properties(self, registry: ToolRegistry) -> None:
        """JSON schema must include distance_km and avg_heart_rate as properties."""
        tools = registry.get_anthropic_tools()
        schema = tools[0]["input_schema"]
        props = schema.get("properties", {})
        assert "distance_km" in props
        assert "avg_heart_rate" in props

    def test_description_mentions_tss(self, registry: ToolRegistry) -> None:
        """Tool description must mention TSS for LLM discoverability."""
        tools = registry.get_anthropic_tools()
        assert "TSS" in tools[0]["description"]

    def test_execute_valid_input_succeeds(self, registry: ToolRegistry) -> None:
        """Registry.execute with valid input should return success=True."""
        result = registry.execute("compute_training_stress", _make_input())
        assert result.success is True
        assert "tss" in result.output

    def test_execute_invalid_workout_type_fails(self, registry: ToolRegistry) -> None:
        """Unrecognised workout type should fail validation, not crash."""
        bad_input = _make_input(workout_type="ultramarathon_shuffle")
        result = registry.execute("compute_training_stress", bad_input)
        assert result.success is False
        assert "error" in result.output

    def test_execute_missing_required_field_fails(self, registry: ToolRegistry) -> None:
        """Missing duration_minutes should fail validation."""
        bad_input = {"workout_type": "easy", "intensity": 0.6}
        result = registry.execute("compute_training_stress", bad_input)
        assert result.success is False

    def test_execute_intensity_out_of_range_fails(self, registry: ToolRegistry) -> None:
        """Intensity > 1.0 should fail validation."""
        result = registry.execute(
            "compute_training_stress",
            _make_input(intensity=1.5),
        )
        assert result.success is False

    def test_execute_duration_zero_fails(self, registry: ToolRegistry) -> None:
        """duration_minutes=0 must fail validation."""
        result = registry.execute(
            "compute_training_stress",
            _make_input(duration_minutes=0.0),
        )
        assert result.success is False

    def test_double_registration_raises(self) -> None:
        """Registering the same tool twice must raise ValueError."""
        r = ToolRegistry()
        register(r)
        with pytest.raises(ValueError, match="already registered"):
            register(r)

    def test_to_content_block_is_valid_json(self, registry: ToolRegistry) -> None:
        """ToolResult.to_content_block should return valid JSON."""
        import json

        result = registry.execute("compute_training_stress", _make_input())
        block = result.to_content_block()
        parsed = json.loads(block)
        assert "tss" in parsed

    def test_execute_with_all_optional_fields(self, registry: ToolRegistry) -> None:
        """Full input including optional fields should succeed."""
        full_input = _make_input(
            duration_minutes=75.0,
            intensity=0.80,
            distance_km=15.0,
            avg_heart_rate=155,
        )
        result = registry.execute("compute_training_stress", full_input)
        assert result.success is True
        assert result.output["tss"] > 0


# ---------------------------------------------------------------------------
# Boundary / numerical edge cases
# ---------------------------------------------------------------------------


class TestNumericalEdgeCases:
    """Edge-case numerical correctness tests."""

    def test_very_short_duration_non_zero_tss(self) -> None:
        """Even a 1-minute workout at high intensity should produce non-zero TSS."""
        result = compute_training_stress_handler(_make_input(duration_minutes=1.0, intensity=1.0))
        assert result["tss"] == pytest.approx(100.0 / 60.0, rel=1e-8)

    def test_hr_exactly_at_default_threshold(self) -> None:
        """HR == _DEFAULT_THRESHOLD_HR should give IF=1.0, not > 1."""
        result = compute_training_stress_handler(_make_input(avg_heart_rate=_DEFAULT_THRESHOLD_HR))
        assert result["intensity_factor"] == pytest.approx(1.0)

    def test_easy_workout_below_50_tss(self) -> None:
        """A typical 45-minute easy run should fall in the 'easy' band (< 50 TSS)."""
        result = compute_training_stress_handler(
            _make_input(workout_type="easy", duration_minutes=45.0, intensity=0.60)
        )
        assert result["tss"] < _EASY_CEILING
        assert result["load_classification"] == "easy"

    def test_interval_session_hard_or_higher(self) -> None:
        """A tough interval session should classify as 'hard' or 'very_hard'."""
        result = compute_training_stress_handler(
            _make_input(workout_type="interval", duration_minutes=75.0, intensity=0.95)
        )
        assert result["load_classification"] in ("hard", "very_hard")

    def test_tss_boundary_exactly_50(self) -> None:
        """TSS == 50 should land in 'moderate', not 'easy'."""
        # TSS = (duration_s * IF^2) / 3600 * 100
        # 50 = (d * IF^2) / 36  => d = 50*36 / IF^2 = 1800 / 0.5^2 = 7200s = 120 min
        result = compute_training_stress_handler(
            _make_input(duration_minutes=120.0, intensity=0.5)
        )
        assert result["tss"] == pytest.approx(50.0, rel=1e-8)
        assert result["load_classification"] == "moderate"

    def test_tss_boundary_exactly_100(self) -> None:
        """TSS == 100 should land in 'hard', not 'moderate'."""
        result = compute_training_stress_handler(_make_input(duration_minutes=60.0, intensity=1.0))
        assert result["tss"] == pytest.approx(100.0, rel=1e-8)
        assert result["load_classification"] == "hard"

    def test_tss_boundary_exactly_200(self) -> None:
        """TSS == 200 should land in 'very_hard', not 'hard'."""
        result = compute_training_stress_handler(
            _make_input(duration_minutes=120.0, intensity=1.0)
        )
        assert result["tss"] == pytest.approx(200.0, rel=1e-8)
        assert result["load_classification"] == "very_hard"
