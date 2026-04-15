"""Tests for the Monte Carlo Race Simulation Engine.

Validates stochastic race simulations including baseline pace derivation
from VDOT, environmental adjustments (heat, elevation, wind), fitness/
fatigue factors from TSB, and statistical output (percentiles, confidence
intervals).

Uses seeded RNG for deterministic test results.

References:
    - mountain-software-jp/trail-simulator: Python Monte Carlo reference
    - PRD Section 5.2: Race simulation engine specification
"""

import math

import pytest

from src.deterministic.daniels import RACE_DISTANCES, compute_vdot
from src.deterministic.monte_carlo import (
    DEFAULT_NUM_SIMULATIONS,
    DEFAULT_PACE_CV,
    ELEVATION_GAIN_PENALTY_PER_M,
    HEADWIND_PENALTY_PER_MS,
    HEAT_BASELINE_C,
    HEAT_PENALTY_PER_DEGREE_C,
    TSB_PACE_ADJUSTMENT_PER_UNIT,
    EnvironmentConditions,
    SimulationResult,
    compute_confidence_interval,
    simulate_race,
    simulate_race_from_vdot,
)


class TestConstants:
    """Verify simulation constants are sensible."""

    def test_default_simulations(self) -> None:
        assert DEFAULT_NUM_SIMULATIONS == 10_000

    def test_default_pace_cv(self) -> None:
        assert DEFAULT_PACE_CV == 0.03

    def test_heat_baseline(self) -> None:
        assert HEAT_BASELINE_C == 18.0

    def test_heat_penalty_positive(self) -> None:
        assert HEAT_PENALTY_PER_DEGREE_C > 0

    def test_elevation_penalty_positive(self) -> None:
        assert ELEVATION_GAIN_PENALTY_PER_M > 0

    def test_headwind_penalty_positive(self) -> None:
        assert HEADWIND_PENALTY_PER_MS > 0

    def test_tsb_adjustment_positive(self) -> None:
        assert TSB_PACE_ADJUSTMENT_PER_UNIT > 0


class TestEnvironmentConditions:
    """Tests for the EnvironmentConditions dataclass."""

    def test_defaults(self) -> None:
        env = EnvironmentConditions()
        assert env.temperature_c == HEAT_BASELINE_C
        assert env.elevation_gain_m == 0.0
        assert env.headwind_ms == 0.0

    def test_custom_values(self) -> None:
        env = EnvironmentConditions(temperature_c=30.0, elevation_gain_m=500.0, headwind_ms=3.0)
        assert env.temperature_c == 30.0
        assert env.elevation_gain_m == 500.0
        assert env.headwind_ms == 3.0

    def test_frozen(self) -> None:
        env = EnvironmentConditions()
        with pytest.raises(AttributeError):
            env.temperature_c = 25.0  # type: ignore[misc]


class TestSimulateRace:
    """Tests for the primary simulate_race function."""

    # Reference: 5K in 20:00 → VDOT ≈ 49.8
    FIVE_K = RACE_DISTANCES["5K"]
    REF_TIME = 20.0  # minutes

    def test_returns_simulation_result(self) -> None:
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=100,
            seed=42,
        )
        assert isinstance(result, SimulationResult)

    def test_result_has_all_fields(self) -> None:
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=100,
            seed=42,
        )
        assert result.median_time_minutes > 0
        assert result.mean_time_minutes > 0
        assert result.std_time_minutes >= 0
        assert result.p5_time_minutes > 0
        assert result.p95_time_minutes > 0
        assert result.fastest_time_minutes > 0
        assert result.slowest_time_minutes > 0
        assert result.num_simulations == 100
        assert result.baseline_time_minutes > 0
        assert result.environment_factor > 0
        assert result.fitness_factor > 0

    def test_same_distance_baseline_near_reference(self) -> None:
        """Simulating the same distance as reference should predict ~same time."""
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=5000,
            seed=42,
        )
        # Median should be close to the reference time
        assert result.median_time_minutes == pytest.approx(self.REF_TIME, abs=1.0)

    def test_longer_distance_slower(self) -> None:
        """A marathon should be predicted much slower than a 5K."""
        result_5k = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=100,
            seed=42,
        )
        result_marathon = simulate_race(
            RACE_DISTANCES["marathon"],
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=100,
            seed=42,
        )
        assert result_marathon.median_time_minutes > result_5k.median_time_minutes * 5

    def test_seeded_reproducibility(self) -> None:
        """Same seed should produce identical results."""
        r1 = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=500,
            seed=12345,
        )
        r2 = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=500,
            seed=12345,
        )
        assert r1.median_time_minutes == r2.median_time_minutes
        assert r1.mean_time_minutes == r2.mean_time_minutes

    def test_different_seeds_different_results(self) -> None:
        """Different seeds should (almost certainly) produce different results."""
        r1 = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=500,
            seed=1,
        )
        r2 = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=500,
            seed=2,
        )
        assert r1.median_time_minutes != r2.median_time_minutes

    def test_percentile_ordering(self) -> None:
        """Percentiles should be in ascending order."""
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=1000,
            seed=42,
        )
        assert result.fastest_time_minutes <= result.p5_time_minutes
        assert result.p5_time_minutes <= result.p25_time_minutes
        assert result.p25_time_minutes <= result.median_time_minutes
        assert result.median_time_minutes <= result.p75_time_minutes
        assert result.p75_time_minutes <= result.p95_time_minutes
        assert result.p95_time_minutes <= result.slowest_time_minutes

    def test_zero_pace_cv_no_variance(self) -> None:
        """With zero variance, all simulations should produce the same time."""
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            pace_cv=0.0,
            num_simulations=100,
            seed=42,
        )
        assert result.std_time_minutes == pytest.approx(0.0, abs=1e-10)
        assert result.fastest_time_minutes == result.slowest_time_minutes

    def test_higher_cv_wider_spread(self) -> None:
        """Higher pace_cv should produce wider finish-time spread."""
        r_narrow = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            pace_cv=0.02,
            num_simulations=1000,
            seed=42,
        )
        r_wide = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            pace_cv=0.10,
            num_simulations=1000,
            seed=42,
        )
        assert r_wide.std_time_minutes > r_narrow.std_time_minutes

    def test_num_simulations_respected(self) -> None:
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=50,
            seed=42,
        )
        assert result.num_simulations == 50


class TestSimulateRaceFromVDOT:
    """Tests for the VDOT-based simulation entry point."""

    def test_basic_simulation(self) -> None:
        result = simulate_race_from_vdot(
            vdot=50.0,
            distance_meters=5000.0,
            num_simulations=100,
            seed=42,
        )
        assert isinstance(result, SimulationResult)
        assert result.median_time_minutes > 0

    def test_matches_race_based_simulation(self) -> None:
        """VDOT-based and race-based should produce similar baselines."""
        # 5K in 20:00 gives VDOT ~49.8
        vdot = compute_vdot(5000.0, 20.0)
        result_vdot = simulate_race_from_vdot(
            vdot=vdot,
            distance_meters=5000.0,
            num_simulations=1000,
            seed=42,
        )
        result_race = simulate_race(
            5000.0,
            5000.0,
            20.0,
            num_simulations=1000,
            seed=42,
        )
        # Baselines should be identical
        assert result_vdot.baseline_time_minutes == pytest.approx(
            result_race.baseline_time_minutes, rel=1e-6
        )

    def test_higher_vdot_faster_times(self) -> None:
        r_low = simulate_race_from_vdot(
            vdot=40.0,
            distance_meters=5000.0,
            num_simulations=100,
            seed=42,
        )
        r_high = simulate_race_from_vdot(
            vdot=60.0,
            distance_meters=5000.0,
            num_simulations=100,
            seed=42,
        )
        assert r_high.median_time_minutes < r_low.median_time_minutes


class TestEnvironmentEffects:
    """Tests for environmental condition adjustments."""

    FIVE_K = RACE_DISTANCES["5K"]
    REF_TIME = 20.0

    def test_heat_slows_pace(self) -> None:
        """Hot conditions should produce slower predicted times."""
        r_cool = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(temperature_c=18.0),
            num_simulations=500,
            seed=42,
        )
        r_hot = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(temperature_c=35.0),
            num_simulations=500,
            seed=42,
        )
        assert r_hot.median_time_minutes > r_cool.median_time_minutes

    def test_cool_no_penalty(self) -> None:
        """Below-baseline temperature should have no heat penalty."""
        r_default = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=500,
            seed=42,
        )
        r_cool = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(temperature_c=10.0),
            num_simulations=500,
            seed=42,
        )
        # Should be the same — no cold penalty modeled
        assert r_cool.environment_factor == r_default.environment_factor

    def test_elevation_slows_pace(self) -> None:
        """Course with elevation gain should be slower."""
        r_flat = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(elevation_gain_m=0.0),
            num_simulations=500,
            seed=42,
        )
        r_hilly = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(elevation_gain_m=300.0),
            num_simulations=500,
            seed=42,
        )
        assert r_hilly.median_time_minutes > r_flat.median_time_minutes

    def test_headwind_slows_pace(self) -> None:
        """Headwind should produce slower times."""
        r_calm = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(headwind_ms=0.0),
            num_simulations=500,
            seed=42,
        )
        r_windy = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(headwind_ms=5.0),
            num_simulations=500,
            seed=42,
        )
        assert r_windy.median_time_minutes > r_calm.median_time_minutes

    def test_tailwind_helps(self) -> None:
        """Tailwind (negative headwind) should produce faster times."""
        r_calm = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(headwind_ms=0.0),
            num_simulations=500,
            seed=42,
        )
        r_tailwind = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(headwind_ms=-3.0),
            num_simulations=500,
            seed=42,
        )
        assert r_tailwind.median_time_minutes < r_calm.median_time_minutes

    def test_environment_factor_neutral_by_default(self) -> None:
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=100,
            seed=42,
        )
        assert result.environment_factor == pytest.approx(1.0, abs=1e-10)

    def test_combined_adverse_conditions(self) -> None:
        """Multiple adverse factors should compound."""
        r_default = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            num_simulations=500,
            seed=42,
        )
        r_adverse = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            environment=EnvironmentConditions(
                temperature_c=32.0,
                elevation_gain_m=200.0,
                headwind_ms=4.0,
            ),
            num_simulations=500,
            seed=42,
        )
        assert r_adverse.environment_factor > r_default.environment_factor


class TestFitnessEffects:
    """Tests for TSB-based fitness/fatigue adjustments."""

    FIVE_K = RACE_DISTANCES["5K"]
    REF_TIME = 20.0

    def test_positive_tsb_faster(self) -> None:
        """Positive TSB (fresh) should predict faster times."""
        r_neutral = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            tsb=0.0,
            num_simulations=500,
            seed=42,
        )
        r_fresh = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            tsb=20.0,
            num_simulations=500,
            seed=42,
        )
        assert r_fresh.median_time_minutes < r_neutral.median_time_minutes

    def test_negative_tsb_slower(self) -> None:
        """Negative TSB (fatigued) should predict slower times."""
        r_neutral = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            tsb=0.0,
            num_simulations=500,
            seed=42,
        )
        r_fatigued = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            tsb=-30.0,
            num_simulations=500,
            seed=42,
        )
        assert r_fatigued.median_time_minutes > r_neutral.median_time_minutes

    def test_zero_tsb_neutral(self) -> None:
        """Zero TSB should produce fitness_factor of 1.0."""
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            tsb=0.0,
            num_simulations=100,
            seed=42,
        )
        assert result.fitness_factor == pytest.approx(1.0, abs=1e-10)

    def test_fitness_factor_floored(self) -> None:
        """Extreme positive TSB should not produce factor below 0.8."""
        result = simulate_race(
            self.FIVE_K,
            self.FIVE_K,
            self.REF_TIME,
            tsb=500.0,
            num_simulations=100,
            seed=42,
        )
        assert result.fitness_factor >= 0.8


class TestComputeConfidenceInterval:
    """Tests for the confidence interval helper."""

    def test_90_percent_interval(self) -> None:
        times = list(range(1, 101))  # 1 to 100
        lo, hi = compute_confidence_interval(times, confidence=0.90)
        assert lo <= 6  # ~5th percentile
        assert hi >= 95  # ~95th percentile

    def test_narrow_confidence(self) -> None:
        times = list(range(1, 101))
        lo_50, hi_50 = compute_confidence_interval(times, confidence=0.50)
        lo_90, hi_90 = compute_confidence_interval(times, confidence=0.90)
        # Wider confidence should produce wider interval
        assert (hi_90 - lo_90) > (hi_50 - lo_50)

    def test_single_value(self) -> None:
        lo, hi = compute_confidence_interval([42.0], confidence=0.90)
        assert lo == 42.0
        assert hi == 42.0

    def test_ordered_output(self) -> None:
        times = [10.0, 20.0, 30.0, 40.0, 50.0]
        lo, hi = compute_confidence_interval(times, confidence=0.90)
        assert lo <= hi

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            compute_confidence_interval([], confidence=0.90)

    def test_invalid_confidence_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            compute_confidence_interval([1.0, 2.0], confidence=0.0)

    def test_invalid_confidence_one_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            compute_confidence_interval([1.0, 2.0], confidence=1.0)

    def test_invalid_confidence_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            compute_confidence_interval([1.0, 2.0], confidence=-0.5)


class TestInputValidation:
    """Tests for input validation across Monte Carlo functions."""

    def test_zero_distance_raises(self) -> None:
        with pytest.raises(ValueError, match="distance_meters.*positive"):
            simulate_race(0.0, 5000.0, 20.0, num_simulations=10, seed=42)

    def test_negative_distance_raises(self) -> None:
        with pytest.raises(ValueError, match="distance_meters.*positive"):
            simulate_race(-100.0, 5000.0, 20.0, num_simulations=10, seed=42)

    def test_zero_ref_distance_raises(self) -> None:
        with pytest.raises(ValueError, match="recent_race_distance.*positive"):
            simulate_race(5000.0, 0.0, 20.0, num_simulations=10, seed=42)

    def test_zero_ref_time_raises(self) -> None:
        with pytest.raises(ValueError, match="recent_race_time.*positive"):
            simulate_race(5000.0, 5000.0, 0.0, num_simulations=10, seed=42)

    def test_negative_pace_cv_raises(self) -> None:
        with pytest.raises(ValueError, match="pace_cv.*non-negative"):
            simulate_race(5000.0, 5000.0, 20.0, pace_cv=-0.1, num_simulations=10, seed=42)

    def test_zero_num_simulations_raises(self) -> None:
        with pytest.raises(ValueError, match="num_simulations.*positive"):
            simulate_race(5000.0, 5000.0, 20.0, num_simulations=0, seed=42)

    # --- simulate_race_from_vdot validation ---

    def test_vdot_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="vdot.*positive"):
            simulate_race_from_vdot(0.0, 5000.0, num_simulations=10, seed=42)

    def test_vdot_negative_distance_raises(self) -> None:
        with pytest.raises(ValueError, match="distance_meters.*positive"):
            simulate_race_from_vdot(50.0, -100.0, num_simulations=10, seed=42)

    def test_vdot_negative_pace_cv_raises(self) -> None:
        with pytest.raises(ValueError, match="pace_cv.*non-negative"):
            simulate_race_from_vdot(50.0, 5000.0, pace_cv=-0.01, num_simulations=10, seed=42)

    def test_vdot_zero_simulations_raises(self) -> None:
        with pytest.raises(ValueError, match="num_simulations.*positive"):
            simulate_race_from_vdot(50.0, 5000.0, num_simulations=0, seed=42)


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_single_simulation(self) -> None:
        """A single simulation should still produce valid output."""
        result = simulate_race(
            5000.0,
            5000.0,
            20.0,
            num_simulations=1,
            seed=42,
        )
        assert result.num_simulations == 1
        assert result.fastest_time_minutes == result.slowest_time_minutes

    def test_very_short_distance(self) -> None:
        """Very short race distance should not crash."""
        result = simulate_race(
            1500.0,
            5000.0,
            20.0,
            num_simulations=100,
            seed=42,
        )
        assert result.median_time_minutes > 0
        assert result.median_time_minutes < 20.0  # Shorter than 5K

    def test_very_long_distance(self) -> None:
        """Marathon-length simulation should work."""
        result = simulate_race(
            42195.0,
            5000.0,
            20.0,
            num_simulations=100,
            seed=42,
        )
        assert result.median_time_minutes > 100  # Marathons take 2+ hours

    def test_all_times_positive(self) -> None:
        """All simulated times should be positive even with high variance."""
        result = simulate_race(
            5000.0,
            5000.0,
            20.0,
            pace_cv=0.20,
            num_simulations=1000,
            seed=42,
        )
        assert result.fastest_time_minutes > 0

    def test_simulation_result_frozen(self) -> None:
        result = simulate_race(
            5000.0,
            5000.0,
            20.0,
            num_simulations=10,
            seed=42,
        )
        with pytest.raises(AttributeError):
            result.median_time_minutes = 999.0  # type: ignore[misc]

    def test_extreme_heat(self) -> None:
        """Extreme heat should slow but not break simulation."""
        result = simulate_race(
            5000.0,
            5000.0,
            20.0,
            environment=EnvironmentConditions(temperature_c=45.0),
            num_simulations=100,
            seed=42,
        )
        assert result.environment_factor > 1.0
        assert math.isfinite(result.median_time_minutes)

    def test_extreme_elevation(self) -> None:
        """Extreme elevation gain should slow but not break simulation."""
        result = simulate_race(
            5000.0,
            5000.0,
            20.0,
            environment=EnvironmentConditions(elevation_gain_m=2000.0),
            num_simulations=100,
            seed=42,
        )
        assert result.environment_factor > 1.0
        assert math.isfinite(result.median_time_minutes)

    def test_strong_tailwind_factor_floored(self) -> None:
        """Extreme tailwind should not produce environment factor below 0.5."""
        result = simulate_race(
            5000.0,
            5000.0,
            20.0,
            environment=EnvironmentConditions(headwind_ms=-200.0),
            num_simulations=100,
            seed=42,
        )
        assert result.environment_factor >= 0.5
