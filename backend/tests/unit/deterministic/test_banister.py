"""Tests for the Banister Impulse-Response (Fitness-Fatigue) model.

Validates CTL, ATL, and TSB calculations against known exercise science
literature values and expected mathematical properties of exponential
moving averages.

Reference values:
    - CTL after 30 days at 50 TSS/day (τ=42): ~25.6
    - ATL after 30 days at 50 TSS/day (τ=7): ~49.2
    - TSB = CTL - ATL by definition
"""

import math

import pytest

from src.deterministic.banister import (
    DEFAULT_FATIGUE_TAU,
    DEFAULT_FITNESS_TAU,
    classify_recovery_status,
    compute_atl,
    compute_ctl,
    compute_ema_series,
    compute_tsb,
    compute_tsb_series,
)


class TestComputeCTL:
    """Tests for Chronic Training Load (fitness) calculation."""

    @pytest.fixture
    def steady_state_load(self) -> list[float]:
        """30 days of constant 50 TSS/day training."""
        return [50.0] * 30

    def test_ctl_steady_state(self, steady_state_load: list[float]) -> None:
        """CTL after 30 days at 50 TSS/day with τ=42 should be ~25.6.

        This is a known reference value from exercise science literature,
        confirmed in the exercise-science SKILL.md.
        """
        ctl = compute_ctl(steady_state_load, tau=42)
        assert ctl == pytest.approx(25.6, abs=0.5)

    def test_ctl_mathematically_exact(self, steady_state_load: list[float]) -> None:
        """Verify CTL matches the closed-form EMA formula.

        For constant load L over n days with time constant τ:
        EMA_n = L * (1 - e^(-n/τ))
        """
        tau = 42
        expected = 50.0 * (1 - math.exp(-30 / tau))
        ctl = compute_ctl(steady_state_load, tau=tau)
        assert ctl == pytest.approx(expected, rel=1e-10)

    def test_ctl_default_tau_is_42(self) -> None:
        """Default fitness time constant should be 42 days."""
        assert DEFAULT_FITNESS_TAU == 42

    def test_ctl_single_day(self) -> None:
        """A single day of load should produce a small CTL."""
        ctl = compute_ctl([100.0], tau=42)
        expected = 100.0 * (1 - math.exp(-1 / 42))
        assert ctl == pytest.approx(expected, rel=1e-10)
        assert ctl < 3.0  # Sanity: one day barely moves 42-day EMA

    def test_ctl_with_initial_value(self) -> None:
        """Pre-existing CTL should be incorporated into calculation."""
        ctl_with_initial = compute_ctl([0.0] * 10, tau=42, initial_ctl=50.0)
        # 10 days of rest from CTL=50 should decay but stay well above 0
        assert 30.0 < ctl_with_initial < 50.0

    @pytest.mark.parametrize("tau,expected_range", [
        (42, (20, 30)),    # Standard fitness decay
        (7, (45, 52)),     # Fast adaptation (acts like ATL)
        (100, (10, 18)),   # Very slow adaptation
    ])
    def test_ctl_varies_with_tau(
        self,
        steady_state_load: list[float],
        tau: int,
        expected_range: tuple[float, float],
    ) -> None:
        """Different time constants produce different adaptation rates.

        Smaller τ → faster response → closer to the input load.
        Larger τ → slower response → lags further behind.
        """
        ctl = compute_ctl(steady_state_load, tau=tau)
        assert expected_range[0] <= ctl <= expected_range[1]


class TestComputeATL:
    """Tests for Acute Training Load (fatigue) calculation."""

    @pytest.fixture
    def steady_state_load(self) -> list[float]:
        """30 days of constant 50 TSS/day training."""
        return [50.0] * 30

    def test_atl_steady_state(self, steady_state_load: list[float]) -> None:
        """ATL after 30 days at 50 TSS/day with τ=7 should be ~49.2.

        With τ=7 and 30 days of constant load, ATL should nearly
        converge to the load value (50), reaching ~49.2.
        """
        atl = compute_atl(steady_state_load, tau=7)
        assert atl == pytest.approx(49.2, abs=0.5)

    def test_atl_default_tau_is_7(self) -> None:
        """Default fatigue time constant should be 7 days."""
        assert DEFAULT_FATIGUE_TAU == 7

    def test_atl_converges_faster_than_ctl(self, steady_state_load: list[float]) -> None:
        """ATL (τ=7) should be closer to load than CTL (τ=42) after same period."""
        atl = compute_atl(steady_state_load, tau=7)
        ctl = compute_ctl(steady_state_load, tau=42)
        load = 50.0
        assert abs(atl - load) < abs(ctl - load)

    def test_atl_with_initial_value(self) -> None:
        """Pre-existing ATL should decay quickly with τ=7."""
        atl = compute_atl([0.0] * 10, tau=7, initial_atl=50.0)
        # 10 days of rest with τ=7 should drop ATL significantly
        assert atl < 15.0


class TestComputeTSB:
    """Tests for Training Stress Balance (form) calculation."""

    @pytest.fixture
    def steady_state_load(self) -> list[float]:
        """30 days of constant 50 TSS/day training."""
        return [50.0] * 30

    def test_tsb_is_ctl_minus_atl(self, steady_state_load: list[float]) -> None:
        """TSB = CTL - ATL by definition."""
        ctl = compute_ctl(steady_state_load, tau=42)
        atl = compute_atl(steady_state_load, tau=7)
        tsb = compute_tsb(steady_state_load)
        assert tsb == pytest.approx(ctl - atl, abs=0.01)

    def test_tsb_negative_during_heavy_training(self, steady_state_load: list[float]) -> None:
        """During sustained training, TSB should be negative.

        Fatigue (ATL) responds faster than fitness (CTL), so during
        ongoing training the athlete is in a fatigued state.
        """
        tsb = compute_tsb(steady_state_load)
        assert tsb < 0

    def test_tsb_positive_after_rest(self) -> None:
        """After a rest period following training, TSB should become positive.

        Fatigue dissipates faster than fitness, creating a positive
        TSB (freshness) window — the basis of tapering.
        """
        heavy_then_rest = [80.0] * 30 + [0.0] * 21
        tsb = compute_tsb(heavy_then_rest)
        assert tsb > 0

    def test_tsb_custom_time_constants(self) -> None:
        """TSB should respect custom τ values for both CTL and ATL."""
        loads = [50.0] * 20
        tsb_default = compute_tsb(loads)
        tsb_custom = compute_tsb(loads, fitness_tau=60, fatigue_tau=10)
        assert tsb_default != pytest.approx(tsb_custom, abs=0.1)


class TestDecayBehavior:
    """Tests for correct exponential decay properties."""

    def test_zero_load_decays_to_zero(self) -> None:
        """With no training, fitness should decay toward zero.

        After 100 rest days following 10 days of training, CTL should
        be negligible due to exponential decay.
        """
        load = [100.0] * 10 + [0.0] * 100
        ctl = compute_ctl(load, tau=42)
        assert ctl < 5.0

    def test_decay_rate_matches_time_constant(self) -> None:
        """After exactly τ days of rest, EMA should decay to ~36.8% of peak.

        The decay factor per day is e^(-1/τ), so after τ days the
        remaining fraction is e^(-τ/τ) = e^(-1) ≈ 0.368.
        """
        # Build up CTL with long steady training, then rest for exactly τ days
        tau = 42
        build = [50.0] * 200  # Long enough to reach near-steady state
        peak_ctl = compute_ctl(build, tau=tau)

        rest = build + [0.0] * tau
        decayed_ctl = compute_ctl(rest, tau=tau)

        ratio = decayed_ctl / peak_ctl
        assert ratio == pytest.approx(math.exp(-1), abs=0.01)

    def test_monotonic_decay_during_rest(self) -> None:
        """CTL should monotonically decrease during a rest period."""
        loads = [80.0] * 20 + [0.0] * 30
        series = compute_ema_series(loads, tau=42)
        rest_series = series[20:]  # Just the rest portion
        for i in range(1, len(rest_series)):
            assert rest_series[i] < rest_series[i - 1]

    def test_monotonic_increase_during_training(self) -> None:
        """CTL should monotonically increase during constant training from zero."""
        loads = [50.0] * 30
        series = compute_ema_series(loads, tau=42)
        for i in range(1, len(series)):
            assert series[i] > series[i - 1]


class TestEMASeries:
    """Tests for the full EMA series output (for charting)."""

    def test_series_length_matches_input(self) -> None:
        """Output series should have the same length as input."""
        loads = [50.0] * 15
        series = compute_ema_series(loads, tau=42)
        assert len(series) == len(loads)

    def test_series_last_value_matches_scalar(self) -> None:
        """Last value in series should match the scalar CTL computation."""
        loads = [50.0] * 30
        series = compute_ema_series(loads, tau=42)
        scalar = compute_ctl(loads, tau=42)
        assert series[-1] == pytest.approx(scalar, rel=1e-10)

    def test_series_first_value(self) -> None:
        """First value should be load * alpha from initial_value=0."""
        loads = [100.0, 50.0, 75.0]
        series = compute_ema_series(loads, tau=42)
        alpha = 1.0 - math.exp(-1.0 / 42)
        assert series[0] == pytest.approx(100.0 * alpha, rel=1e-10)


class TestTSBSeries:
    """Tests for the full CTL/ATL/TSB series output."""

    def test_returns_all_three_keys(self) -> None:
        """Output dict should contain ctl, atl, and tsb keys."""
        result = compute_tsb_series([50.0] * 10)
        assert set(result.keys()) == {"ctl", "atl", "tsb"}

    def test_all_series_same_length(self) -> None:
        """All three series should be the same length as input."""
        loads = [50.0] * 20
        result = compute_tsb_series(loads)
        assert len(result["ctl"]) == len(loads)
        assert len(result["atl"]) == len(loads)
        assert len(result["tsb"]) == len(loads)

    def test_tsb_series_equals_ctl_minus_atl(self) -> None:
        """TSB series should equal CTL - ATL at every point."""
        loads = [80.0] * 10 + [0.0] * 10
        result = compute_tsb_series(loads)
        for i in range(len(loads)):
            expected = result["ctl"][i] - result["atl"][i]
            assert result["tsb"][i] == pytest.approx(expected, rel=1e-10)


class TestEdgeCases:
    """Tests for input validation and edge cases."""

    def test_empty_history_raises(self) -> None:
        """Empty training history should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            compute_ctl([], tau=42)

    def test_empty_history_raises_atl(self) -> None:
        """Empty training history should raise ValueError for ATL."""
        with pytest.raises(ValueError, match="non-empty"):
            compute_atl([], tau=7)

    def test_empty_history_raises_tsb(self) -> None:
        """Empty training history should raise ValueError for TSB."""
        with pytest.raises(ValueError, match="non-empty"):
            compute_tsb([])

    def test_zero_tau_raises(self) -> None:
        """Zero time constant should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_ctl([50.0], tau=0)

    def test_negative_tau_raises(self) -> None:
        """Negative time constant should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_ctl([50.0], tau=-5)

    def test_negative_loads_accepted(self) -> None:
        """Negative load values should be accepted (e.g., rest credits).

        While unusual, the math is valid for negative inputs.
        """
        result = compute_ctl([-10.0, -20.0], tau=42)
        assert result < 0

    def test_single_element_list(self) -> None:
        """Single-element load list should produce valid result."""
        result = compute_ctl([100.0], tau=42)
        assert result > 0
        assert result < 100.0

    def test_very_large_load(self) -> None:
        """Very large loads should not cause overflow."""
        result = compute_ctl([1e6], tau=42)
        assert math.isfinite(result)

    def test_zero_loads(self) -> None:
        """All-zero loads from initial 0 should stay at 0."""
        result = compute_ctl([0.0] * 30, tau=42)
        assert result == pytest.approx(0.0, abs=1e-15)


class TestClassifyRecoveryStatus:
    """Tests for TSB-based recovery classification."""

    @pytest.mark.parametrize("tsb,expected", [
        (25.0, "fresh"),
        (11.0, "fresh"),
        (10.01, "fresh"),
        (10.0, "neutral"),      # boundary: exactly 10 is neutral, not fresh
        (0.0, "neutral"),
        (-10.0, "neutral"),     # boundary: exactly -10 is neutral
        (-10.01, "fatigued"),
        (-15.0, "fatigued"),
        (-20.0, "fatigued"),    # boundary: exactly -20 is fatigued
        (-20.01, "very_fatigued"),
        (-30.0, "very_fatigued"),
        (-100.0, "very_fatigued"),
    ])
    def test_classification_boundaries(self, tsb: float, expected: str) -> None:
        """Each TSB value maps to the correct recovery status."""
        assert classify_recovery_status(tsb) == expected

    def test_return_type_is_literal(self) -> None:
        """Return value should be one of the four valid statuses."""
        valid = {"fresh", "neutral", "fatigued", "very_fatigued"}
        for tsb in [50.0, 5.0, -15.0, -50.0]:
            assert classify_recovery_status(tsb) in valid
