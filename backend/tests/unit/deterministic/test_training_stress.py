"""Tests for the Training Stress Score deterministic module.

Validates:
- TSS formula correctness (compute_tss)
- Load classification thresholds (classify_load)
- HR-to-IF conversion (hr_to_intensity_factor)
- Intensity scaling for target TSS (scale_intensity_for_target_tss)
- DEFAULT_WORKOUT_INTENSITY table completeness
- DEFAULT_THRESHOLD_HR constant
"""

import pytest

from src.deterministic.training_stress import (
    DEFAULT_THRESHOLD_HR,
    DEFAULT_WORKOUT_INTENSITY,
    classify_load,
    compute_tss,
    hr_to_intensity_factor,
    scale_intensity_for_target_tss,
)

# ---------------------------------------------------------------------------
# compute_tss
# ---------------------------------------------------------------------------


class TestComputeTss:
    """Core TSS formula tests."""

    def test_one_hour_at_threshold_is_100(self) -> None:
        """By definition, 60 min at IF=1.0 yields TSS=100."""
        assert compute_tss(60.0, 1.0) == pytest.approx(100.0)

    def test_zero_duration_yields_zero(self) -> None:
        assert compute_tss(0.0, 0.8) == pytest.approx(0.0)

    def test_zero_intensity_yields_zero(self) -> None:
        assert compute_tss(90.0, 0.0) == pytest.approx(0.0)

    def test_scales_quadratically_with_intensity(self) -> None:
        assert compute_tss(60.0, 1.0) == pytest.approx(4 * compute_tss(60.0, 0.5))

    def test_scales_linearly_with_duration(self) -> None:
        assert compute_tss(60.0, 0.7) == pytest.approx(2 * compute_tss(30.0, 0.7))

    def test_negative_duration_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            compute_tss(-1.0, 0.5)

    def test_intensity_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="\\[0, 1\\]"):
            compute_tss(60.0, 1.1)

    def test_intensity_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="\\[0, 1\\]"):
            compute_tss(60.0, -0.1)


# ---------------------------------------------------------------------------
# classify_load
# ---------------------------------------------------------------------------


class TestClassifyLoad:
    """Load classification boundary tests."""

    @pytest.mark.parametrize(
        "tss,expected",
        [
            (0.0, "easy"),
            (49.99, "easy"),
            (50.0, "moderate"),
            (99.99, "moderate"),
            (100.0, "hard"),
            (199.99, "hard"),
            (200.0, "very_hard"),
            (500.0, "very_hard"),
        ],
    )
    def test_boundaries(self, tss: float, expected: str) -> None:
        assert classify_load(tss) == expected


# ---------------------------------------------------------------------------
# hr_to_intensity_factor
# ---------------------------------------------------------------------------


class TestHrToIntensityFactor:
    """Tests for HR-based intensity factor derivation."""

    def test_at_threshold_gives_one(self) -> None:
        """HR at threshold yields IF=1.0."""
        assert hr_to_intensity_factor(175, 175) == pytest.approx(1.0)

    def test_below_threshold(self) -> None:
        """HR below threshold yields IF < 1.0."""
        result = hr_to_intensity_factor(140, 175)
        assert result == pytest.approx(140 / 175)

    def test_above_threshold_clamped_to_one(self) -> None:
        """HR above threshold is clamped to 1.0."""
        assert hr_to_intensity_factor(200, 175) == pytest.approx(1.0)

    def test_zero_hr_gives_zero(self) -> None:
        """HR of 0 gives IF of 0.0."""
        assert hr_to_intensity_factor(0, 175) == pytest.approx(0.0)

    def test_uses_default_threshold(self) -> None:
        """Without explicit threshold, uses DEFAULT_THRESHOLD_HR."""
        result = hr_to_intensity_factor(140)
        assert result == pytest.approx(140 / DEFAULT_THRESHOLD_HR)

    def test_zero_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            hr_to_intensity_factor(140, 0)

    def test_negative_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            hr_to_intensity_factor(140, -10)


# ---------------------------------------------------------------------------
# scale_intensity_for_target_tss
# ---------------------------------------------------------------------------


class TestScaleIntensityForTargetTss:
    """Tests for intensity scaling derived from TSS formula."""

    def test_scale_factor_one_unchanged(self) -> None:
        """Scale factor of 1.0 should not change intensity."""
        assert scale_intensity_for_target_tss(0.7, 1.0) == pytest.approx(0.7)

    def test_scale_factor_four_doubles_intensity(self) -> None:
        """Scaling TSS by 4x requires doubling IF (since TSS ~ IF^2)."""
        result = scale_intensity_for_target_tss(0.4, 4.0)
        assert result == pytest.approx(0.8)

    def test_scale_factor_zero_gives_zero(self) -> None:
        """Scaling TSS to 0 should give IF=0."""
        assert scale_intensity_for_target_tss(0.8, 0.0) == pytest.approx(0.0)

    def test_clamped_to_one(self) -> None:
        """Result cannot exceed 1.0 even with huge scale factor."""
        result = scale_intensity_for_target_tss(0.8, 100.0)
        assert result == pytest.approx(1.0)

    def test_clamped_to_zero(self) -> None:
        """Zero intensity stays zero regardless of scale."""
        assert scale_intensity_for_target_tss(0.0, 5.0) == pytest.approx(0.0)

    def test_negative_scale_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            scale_intensity_for_target_tss(0.5, -1.0)

    def test_consistent_with_tss_formula(self) -> None:
        """Verify: if we scale intensity, the TSS ratio matches scale_factor."""
        original_if = 0.6
        scale = 2.0
        new_if = scale_intensity_for_target_tss(original_if, scale)
        original_tss = compute_tss(60.0, original_if)
        new_tss = compute_tss(60.0, new_if)
        assert new_tss / original_tss == pytest.approx(scale, rel=1e-9)


# ---------------------------------------------------------------------------
# DEFAULT_WORKOUT_INTENSITY
# ---------------------------------------------------------------------------


class TestDefaultWorkoutIntensity:
    """Tests for the canonical workout intensity table."""

    def test_all_workout_types_present(self) -> None:
        """Every known workout type string should have a default intensity."""
        expected_types = {
            "easy",
            "long_run",
            "tempo",
            "interval",
            "repetition",
            "recovery",
            "marathon_pace",
            "fartlek",
            "hill",
            "rest",
            "cross_train",
        }
        assert set(DEFAULT_WORKOUT_INTENSITY.keys()) == expected_types

    def test_rest_is_zero(self) -> None:
        assert DEFAULT_WORKOUT_INTENSITY["rest"] == 0.0

    def test_all_values_in_range(self) -> None:
        """All default intensities must be in [0, 1]."""
        for wt, intensity in DEFAULT_WORKOUT_INTENSITY.items():
            assert 0.0 <= intensity <= 1.0, f"{wt} intensity {intensity} out of range"

    def test_intensity_ordering(self) -> None:
        """Easy should be less intense than tempo, which is less than interval."""
        d = DEFAULT_WORKOUT_INTENSITY
        assert d["recovery"] < d["easy"] < d["tempo"] < d["interval"] < d["repetition"]


class TestDefaultThresholdHr:
    """Tests for the default lactate threshold HR constant."""

    def test_is_positive_integer(self) -> None:
        assert isinstance(DEFAULT_THRESHOLD_HR, int)
        assert DEFAULT_THRESHOLD_HR > 0

    def test_physiologically_reasonable(self) -> None:
        """Threshold HR should be in a plausible range for adults."""
        assert 150 <= DEFAULT_THRESHOLD_HR <= 200
