"""Tests for the Daniels-Gilbert VO2max, VDOT, and Pace Zone calculations.

Validates VDOT computation, race time prediction, training pace zones,
and Karvonen heart rate zones against known mathematical outputs from
the published Daniels-Gilbert equations.

Reference values are computed directly from the equations:
    VO2(v) = -4.60 + 0.182258*v + 0.000104*v^2
    %VO2max(t) = 0.8 + 0.1894393*e^(-0.012778*t) + 0.2989558*e^(-0.1932605*t)
    VDOT = VO2(v) / %VO2max(t)
"""

import math

import pytest

from src.deterministic.daniels import (
    HR_ZONES,
    RACE_DISTANCES,
    TRAINING_ZONES,
    compute_hr_zones,
    compute_training_paces,
    compute_vdot,
    estimate_hr_max,
    karvonen_hr,
    predict_race_time,
    sustained_vo2max_fraction,
    velocity_to_pace_per_km,
    velocity_to_pace_per_mile,
    velocity_to_vo2,
    vo2_to_velocity,
)

# -----------------------------------------------------------------------
# Precomputed reference values from the Daniels-Gilbert equations
# -----------------------------------------------------------------------
# 5K in 20:00 → v=250 m/min
_5K_VO2 = -4.60 + 0.182258 * 250 + 0.000104 * 250**2  # 47.4645
_5K_PCT = 0.8 + 0.1894393 * math.exp(-0.012778 * 20) + 0.2989558 * math.exp(-0.1932605 * 20)
_5K_VDOT = _5K_VO2 / _5K_PCT  # ~49.81

# Marathon in 3:30:00 (210 min) → v=42195/210 ≈ 200.93 m/min
_MAR_V = 42195.0 / 210.0
_MAR_VO2 = -4.60 + 0.182258 * _MAR_V + 0.000104 * _MAR_V**2
_MAR_PCT = 0.8 + 0.1894393 * math.exp(-0.012778 * 210) + 0.2989558 * math.exp(-0.1932605 * 210)
_MAR_VDOT = _MAR_VO2 / _MAR_PCT  # ~44.56


class TestVelocityToVO2:
    """Tests for the oxygen cost equation."""

    def test_known_velocity(self) -> None:
        """VO2 at 250 m/min should match hand-calculated value."""
        vo2 = velocity_to_vo2(250.0)
        assert vo2 == pytest.approx(_5K_VO2, rel=1e-10)

    def test_higher_velocity_higher_vo2(self) -> None:
        """Running faster should cost more oxygen."""
        slow = velocity_to_vo2(200.0)
        fast = velocity_to_vo2(300.0)
        assert fast > slow

    def test_quadratic_term_matters_at_speed(self) -> None:
        """The v^2 term should contribute meaningfully at high velocity."""
        v = 350.0
        linear_only = -4.60 + 0.182258 * v
        full = velocity_to_vo2(v)
        quadratic_contribution = full - linear_only
        assert quadratic_contribution > 5.0  # 0.000104 * 350^2 = 12.74

    def test_zero_velocity_raises(self) -> None:
        """Zero velocity should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            velocity_to_vo2(0.0)

    def test_negative_velocity_raises(self) -> None:
        """Negative velocity should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            velocity_to_vo2(-100.0)


class TestSustainedVO2maxFraction:
    """Tests for the drop-dead time equation."""

    def test_short_effort_high_fraction(self) -> None:
        """A ~5 minute effort returns >1.0 from the regression.

        The Daniels-Gilbert equation is a regression fit to race data.
        For very short durations (<~8 min) it can exceed 1.0, reflecting
        anaerobic contribution beyond VO2max. This is expected behavior.
        """
        pct = sustained_vo2max_fraction(5.0)
        assert pct > 1.0  # Anaerobic contribution at short durations
        pct_20 = sustained_vo2max_fraction(20.0)
        assert pct > pct_20  # Shorter = higher fraction

    def test_20min_effort(self) -> None:
        """20-minute effort should match precomputed value."""
        pct = sustained_vo2max_fraction(20.0)
        assert pct == pytest.approx(_5K_PCT, rel=1e-10)

    def test_marathon_effort(self) -> None:
        """Marathon duration (~210 min) should sustain ~81% VO2max."""
        pct = sustained_vo2max_fraction(210.0)
        assert pct == pytest.approx(_MAR_PCT, rel=1e-10)
        assert 0.79 <= pct <= 0.85

    def test_longer_effort_lower_fraction(self) -> None:
        """Longer efforts should sustain a lower fraction of VO2max."""
        short = sustained_vo2max_fraction(10.0)
        long = sustained_vo2max_fraction(120.0)
        assert short > long

    def test_converges_to_baseline(self) -> None:
        """For very long efforts, %VO2max should approach 0.8 (the constant term)."""
        pct = sustained_vo2max_fraction(1440.0)  # 24 hours
        assert pct == pytest.approx(0.8, abs=0.001)

    def test_zero_time_raises(self) -> None:
        """Zero duration should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            sustained_vo2max_fraction(0.0)


class TestComputeVDOT:
    """Tests for VDOT calculation from race performances."""

    def test_5k_in_20_minutes(self) -> None:
        """5K in 20:00 should produce VDOT ~49.8.

        Computed directly from the Daniels-Gilbert equations.
        """
        vdot = compute_vdot(5000.0, 20.0)
        assert vdot == pytest.approx(_5K_VDOT, rel=1e-6)
        assert 49.5 <= vdot <= 50.1

    def test_marathon_in_3h30(self) -> None:
        """Marathon in 3:30:00 should produce VDOT ~44.6.

        Computed directly from the Daniels-Gilbert equations.
        """
        vdot = compute_vdot(42195.0, 210.0)
        assert vdot == pytest.approx(_MAR_VDOT, rel=1e-6)
        assert 44.0 <= vdot <= 45.0

    def test_faster_race_higher_vdot(self) -> None:
        """Faster performances should produce higher VDOT scores."""
        slow = compute_vdot(5000.0, 25.0)
        fast = compute_vdot(5000.0, 18.0)
        assert fast > slow

    def test_equivalent_performances_similar_vdot(self) -> None:
        """Equivalent efforts at different distances should give similar VDOT.

        An athlete with the same VDOT should have proportionally scaled
        performances across distances.
        """
        vdot_5k = compute_vdot(5000.0, 20.0)
        # Use predict_race_time to get the equivalent 10K time
        predicted_10k = predict_race_time(vdot_5k, 10000.0)
        vdot_10k = compute_vdot(10000.0, predicted_10k)
        assert vdot_5k == pytest.approx(vdot_10k, rel=1e-4)

    def test_zero_distance_raises(self) -> None:
        """Zero distance should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_vdot(0.0, 20.0)

    def test_zero_time_raises(self) -> None:
        """Zero time should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_vdot(5000.0, 0.0)


class TestVO2ToVelocity:
    """Tests for the inverse VO2 equation."""

    def test_round_trip(self) -> None:
        """velocity_to_vo2 and vo2_to_velocity should be exact inverses."""
        original_velocity = 250.0
        vo2 = velocity_to_vo2(original_velocity)
        recovered = vo2_to_velocity(vo2)
        assert recovered == pytest.approx(original_velocity, rel=1e-10)

    @pytest.mark.parametrize("velocity", [150.0, 200.0, 250.0, 300.0, 350.0])
    def test_round_trip_multiple_velocities(self, velocity: float) -> None:
        """Round-trip should work across a range of realistic velocities."""
        vo2 = velocity_to_vo2(velocity)
        recovered = vo2_to_velocity(vo2)
        assert recovered == pytest.approx(velocity, rel=1e-10)


class TestPredictRaceTime:
    """Tests for race time prediction from VDOT."""

    def test_5k_round_trip(self) -> None:
        """Computing VDOT from a 5K time, then predicting back, should match."""
        original_time = 20.0
        vdot = compute_vdot(5000.0, original_time)
        predicted = predict_race_time(vdot, 5000.0)
        assert predicted == pytest.approx(original_time, abs=0.01)

    def test_marathon_round_trip(self) -> None:
        """VDOT → marathon prediction should round-trip accurately."""
        original_time = 210.0
        vdot = compute_vdot(42195.0, original_time)
        predicted = predict_race_time(vdot, 42195.0)
        assert predicted == pytest.approx(original_time, abs=0.01)

    def test_longer_distance_longer_time(self) -> None:
        """Same VDOT should predict longer times for longer distances."""
        vdot = compute_vdot(5000.0, 20.0)
        time_5k = predict_race_time(vdot, 5000.0)
        time_10k = predict_race_time(vdot, 10000.0)
        time_half = predict_race_time(vdot, 21097.5)
        assert time_5k < time_10k < time_half

    def test_higher_vdot_faster_time(self) -> None:
        """Higher VDOT should predict faster times."""
        fast = predict_race_time(55.0, 5000.0)
        slow = predict_race_time(40.0, 5000.0)
        assert fast < slow

    def test_zero_vdot_raises(self) -> None:
        """Zero VDOT should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            predict_race_time(0.0, 5000.0)


class TestTrainingPaces:
    """Tests for training pace zone computation."""

    @pytest.fixture
    def paces_50(self) -> dict[str, tuple[float, float]]:
        """Training paces for VDOT 50."""
        return compute_training_paces(50.0)

    def test_all_zones_present(self, paces_50: dict[str, tuple[float, float]]) -> None:
        """All five standard Daniels zones should be present."""
        assert set(paces_50.keys()) == set(TRAINING_ZONES.keys())

    def test_easy_slower_than_threshold(self, paces_50: dict[str, tuple[float, float]]) -> None:
        """Easy pace should be slower (higher sec/km) than threshold pace."""
        easy_slow = paces_50["easy"][1]
        threshold_fast = paces_50["threshold"][0]
        assert easy_slow > threshold_fast

    def test_interval_faster_than_threshold(
        self, paces_50: dict[str, tuple[float, float]]
    ) -> None:
        """Interval pace should be faster (lower sec/km) than threshold pace."""
        interval_fast = paces_50["interval"][0]
        threshold_slow = paces_50["threshold"][1]
        assert interval_fast < threshold_slow

    def test_repetition_fastest(self, paces_50: dict[str, tuple[float, float]]) -> None:
        """Repetition zone should contain the fastest paces."""
        rep_fast = paces_50["repetition"][0]
        interval_fast = paces_50["interval"][0]
        assert rep_fast < interval_fast

    def test_higher_vdot_faster_paces(self) -> None:
        """Higher VDOT should produce faster paces in every zone."""
        paces_40 = compute_training_paces(40.0)
        paces_60 = compute_training_paces(60.0)
        for zone in TRAINING_ZONES:
            assert paces_60[zone][0] < paces_40[zone][0]

    def test_pace_values_are_realistic(self, paces_50: dict[str, tuple[float, float]]) -> None:
        """Paces for VDOT 50 should be in realistic ranges.

        VDOT 50 is roughly a 19:30 5K runner. Easy pace should be
        around 5:30-7:00/km, threshold around 4:15-4:30/km.
        """
        easy_slow_min_per_km = paces_50["easy"][1] / 60
        assert 5.0 <= easy_slow_min_per_km <= 8.0

        threshold_fast_min_per_km = paces_50["threshold"][0] / 60
        assert 3.5 <= threshold_fast_min_per_km <= 5.0

    def test_zero_vdot_raises(self) -> None:
        """Zero VDOT should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_training_paces(0.0)


class TestPaceConversions:
    """Tests for velocity-to-pace conversion utilities."""

    def test_pace_per_km(self) -> None:
        """250 m/min = 4 min/km = 240 sec/km."""
        pace = velocity_to_pace_per_km(250.0)
        assert pace == pytest.approx(240.0, rel=1e-10)

    def test_pace_per_mile(self) -> None:
        """Pace per mile should be ~1.609x pace per km."""
        pace_km = velocity_to_pace_per_km(250.0)
        pace_mile = velocity_to_pace_per_mile(250.0)
        assert pace_mile == pytest.approx(pace_km * 1.609344, rel=1e-6)

    def test_zero_velocity_raises_km(self) -> None:
        """Zero velocity should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            velocity_to_pace_per_km(0.0)

    def test_zero_velocity_raises_mile(self) -> None:
        """Zero velocity should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            velocity_to_pace_per_mile(0.0)


class TestKarvonenHR:
    """Tests for Karvonen heart rate calculations."""

    def test_karvonen_at_70_percent(self) -> None:
        """70% HRR with HRmax=190, HRrest=50 should be 148 bpm.

        THR = 50 + 0.70 * (190 - 50) = 50 + 98 = 148
        """
        hr = karvonen_hr(190, 50, 0.70)
        assert hr == 148

    def test_karvonen_at_zero_intensity(self) -> None:
        """0% intensity should equal resting HR."""
        hr = karvonen_hr(190, 50, 0.0)
        assert hr == 50

    def test_karvonen_at_full_intensity(self) -> None:
        """100% intensity should equal max HR."""
        hr = karvonen_hr(190, 50, 1.0)
        assert hr == 190

    def test_invalid_hr_max_raises(self) -> None:
        """HRmax <= HRrest should raise ValueError."""
        with pytest.raises(ValueError, match="greater than"):
            karvonen_hr(50, 60, 0.70)

    def test_invalid_intensity_raises(self) -> None:
        """Intensity outside [0, 1] should raise ValueError."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            karvonen_hr(190, 50, 1.5)


class TestHRZones:
    """Tests for heart rate zone computation."""

    def test_all_zones_present(self) -> None:
        """All four HR zones should be computed."""
        zones = compute_hr_zones(190, 50)
        assert set(zones.keys()) == set(HR_ZONES.keys())

    def test_zones_are_ordered(self) -> None:
        """Higher-intensity zones should have higher HR targets."""
        zones = compute_hr_zones(190, 50)
        assert (
            zones["easy"][1] <= zones["threshold"][0] or zones["easy"][1] <= zones["threshold"][1]
        )
        assert zones["threshold"][1] <= zones["interval"][1]

    def test_easy_zone_values(self) -> None:
        """Easy zone should be 60-75% HRR."""
        zones = compute_hr_zones(190, 50)
        assert zones["easy"] == (karvonen_hr(190, 50, 0.60), karvonen_hr(190, 50, 0.75))

    def test_invalid_hr_raises(self) -> None:
        """HRmax <= HRrest should raise ValueError."""
        with pytest.raises(ValueError, match="greater than"):
            compute_hr_zones(50, 60)


class TestEstimateHRMax:
    """Tests for HR max estimation formulas."""

    def test_tanaka_age_30(self) -> None:
        """Tanaka formula for age 30: 208 - 0.7*30 = 187."""
        assert estimate_hr_max(30, method="tanaka") == 187

    def test_fox_age_30(self) -> None:
        """Fox formula for age 30: 220 - 30 = 190."""
        assert estimate_hr_max(30, method="fox") == 190

    def test_tanaka_is_default(self) -> None:
        """Default method should be Tanaka (more accurate)."""
        assert estimate_hr_max(40) == estimate_hr_max(40, method="tanaka")

    def test_older_athlete_lower_hr_max(self) -> None:
        """Older athletes should have lower estimated HR max."""
        young = estimate_hr_max(25)
        old = estimate_hr_max(55)
        assert old < young

    def test_invalid_age_raises(self) -> None:
        """Non-positive age should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            estimate_hr_max(0)

    def test_unknown_method_raises(self) -> None:
        """Unknown estimation method should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown method"):
            estimate_hr_max(30, method="invalid")


class TestRaceDistanceConstants:
    """Tests for standard race distance constants."""

    def test_5k_distance(self) -> None:
        """5K should be exactly 5000 meters."""
        assert RACE_DISTANCES["5K"] == 5000.0

    def test_marathon_distance(self) -> None:
        """Marathon should be 42195 meters."""
        assert RACE_DISTANCES["marathon"] == 42195.0

    def test_mile_distance(self) -> None:
        """Mile should be 1609.344 meters."""
        assert RACE_DISTANCES["mile"] == 1609.344


class TestCoverageGaps:
    """Tests specifically targeting uncovered code paths."""

    def test_vo2_to_velocity_negative_discriminant(self) -> None:
        """Extremely low VO2 should produce negative discriminant error.

        The quadratic _VO2_C*v^2 + _VO2_B*v + (_VO2_A - vo2) = 0 has
        no real solution when vo2 < _VO2_A - B^2/(4*C) ≈ -84.45.
        """
        with pytest.raises(ValueError, match="negative discriminant"):
            vo2_to_velocity(-100.0)

    def test_predict_race_time_negative_distance(self) -> None:
        """Negative distance in predict_race_time should raise ValueError."""
        with pytest.raises(ValueError, match="distance_meters.*positive"):
            predict_race_time(50.0, -5000.0)

    def test_predict_race_time_no_solution(self) -> None:
        """Extreme VDOT/distance combo with no bisection solution should raise.

        An absurdly high VDOT with a very short distance can cause the
        residual function to have the same sign at both bounds, meaning
        no root exists in the search range.
        """
        # VDOT of 200 is far beyond any human — at very short distances
        # the predicted time would be below the 3.5 min lower bound
        with pytest.raises(ValueError, match="No solution found"):
            predict_race_time(200.0, 100.0)  # 100m at superhuman VDOT
