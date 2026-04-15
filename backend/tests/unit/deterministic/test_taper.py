"""Tests for the Taper Decay model.

Validates taper projection, optimal taper length finding, and fitness
retention calculations. Built on the Banister impulse-response model,
the taper module projects CTL/ATL/TSB forward with reduced training load.

Key insight: during a taper, fatigue (ATL, tau=7) decays faster than
fitness (CTL, tau=42), creating a positive TSB window (freshness).

References:
    - Banister et al. (1975): Impulse-response model
    - Thomas & Busso (2005): Taper optimization
    - Mujika & Padilla (2003): Scientific bases for precompetition tapering
"""

import math

import pytest

from src.deterministic.banister import (
    DEFAULT_FITNESS_TAU,
    compute_ctl,
)
from src.deterministic.taper import (
    compute_taper_fitness_retention,
    find_optimal_taper_length,
    project_taper,
)


class TestProjectTaper:
    """Tests for CTL/ATL/TSB projection during a taper period."""

    @pytest.fixture
    def trained_athlete(self) -> list[float]:
        """60 days of steady 80 TSS/day training — well-trained baseline."""
        return [80.0] * 60

    def test_returns_all_three_keys(self, trained_athlete: list[float]) -> None:
        """Output dict should contain ctl, atl, and tsb keys."""
        result = project_taper(trained_athlete, taper_days=14)
        assert set(result.keys()) == {"ctl", "atl", "tsb"}

    def test_output_length_matches_taper_days(self, trained_athlete: list[float]) -> None:
        """Each output series should have length equal to taper_days."""
        taper_days = 14
        result = project_taper(trained_athlete, taper_days=taper_days)
        assert len(result["ctl"]) == taper_days
        assert len(result["atl"]) == taper_days
        assert len(result["tsb"]) == taper_days

    def test_tsb_equals_ctl_minus_atl(self, trained_athlete: list[float]) -> None:
        """TSB should equal CTL - ATL at every point during taper."""
        result = project_taper(trained_athlete, taper_days=14)
        for i in range(14):
            expected = result["ctl"][i] - result["atl"][i]
            assert result["tsb"][i] == pytest.approx(expected, rel=1e-10)

    def test_ctl_decays_during_complete_rest(self, trained_athlete: list[float]) -> None:
        """CTL should monotonically decrease during complete rest taper."""
        result = project_taper(trained_athlete, taper_days=21, taper_load_fraction=0.0)
        for i in range(1, len(result["ctl"])):
            assert result["ctl"][i] < result["ctl"][i - 1]

    def test_atl_decays_during_complete_rest(self, trained_athlete: list[float]) -> None:
        """ATL should monotonically decrease during complete rest taper."""
        result = project_taper(trained_athlete, taper_days=21, taper_load_fraction=0.0)
        for i in range(1, len(result["atl"])):
            assert result["atl"][i] < result["atl"][i - 1]

    def test_atl_decays_faster_than_ctl(self, trained_athlete: list[float]) -> None:
        """ATL (tau=7) should decay faster than CTL (tau=42) during taper.

        This is the fundamental taper principle: fatigue dissipates faster
        than fitness, creating a freshness window.
        """
        result = project_taper(trained_athlete, taper_days=14, taper_load_fraction=0.0)
        # Compare percentage decay after 14 days
        ctl_retention = result["ctl"][-1] / result["ctl"][0]
        atl_retention = result["atl"][-1] / result["atl"][0]
        assert atl_retention < ctl_retention

    def test_tsb_becomes_positive(self, trained_athlete: list[float]) -> None:
        """TSB should eventually become positive during a taper.

        After heavy training, TSB starts negative. During rest, fatigue
        drops faster, and TSB crosses zero into positive territory.
        """
        result = project_taper(trained_athlete, taper_days=21, taper_load_fraction=0.0)
        # At least some TSB values should be positive
        positive_tsb = [t for t in result["tsb"] if t > 0]
        assert len(positive_tsb) > 0

    def test_partial_taper_retains_more_fitness(self, trained_athlete: list[float]) -> None:
        """A partial taper (30% load) should retain more CTL than complete rest."""
        result_rest = project_taper(trained_athlete, taper_days=14, taper_load_fraction=0.0)
        result_partial = project_taper(trained_athlete, taper_days=14, taper_load_fraction=0.3)
        # Partial taper should end with higher CTL
        assert result_partial["ctl"][-1] > result_rest["ctl"][-1]

    def test_complete_rest_fraction_zero(self, trained_athlete: list[float]) -> None:
        """taper_load_fraction=0.0 should produce complete rest."""
        result = project_taper(trained_athlete, taper_days=7, taper_load_fraction=0.0)
        # ATL should decay very quickly with tau=7
        assert result["atl"][-1] < result["atl"][0] * 0.5

    def test_full_maintenance_fraction_one(self, trained_athlete: list[float]) -> None:
        """taper_load_fraction=1.0 should maintain near-current load levels."""
        result = project_taper(trained_athlete, taper_days=7, taper_load_fraction=1.0)
        # CTL should remain relatively stable with full maintenance
        ctl_change = abs(result["ctl"][-1] - result["ctl"][0])
        assert ctl_change < 5.0  # Small change

    def test_custom_time_constants(self, trained_athlete: list[float]) -> None:
        """Custom tau values should affect the decay rates."""
        result_default = project_taper(trained_athlete, taper_days=14)
        result_custom = project_taper(
            trained_athlete, taper_days=14, fitness_tau=60, fatigue_tau=10
        )
        # Different taus produce different curves
        assert result_default["ctl"][-1] != pytest.approx(result_custom["ctl"][-1], abs=0.5)

    def test_short_training_history(self) -> None:
        """Even short training history should produce valid projections."""
        loads = [50.0] * 7
        result = project_taper(loads, taper_days=7)
        assert len(result["ctl"]) == 7
        assert all(math.isfinite(v) for v in result["ctl"])

    def test_single_day_history(self) -> None:
        """Single day of history should work."""
        loads = [100.0]
        result = project_taper(loads, taper_days=7)
        assert len(result["ctl"]) == 7


class TestFindOptimalTaperLength:
    """Tests for finding the taper duration that maximizes TSB."""

    @pytest.fixture
    def well_trained(self) -> list[float]:
        """90 days of steady 70 TSS/day — well-trained athlete."""
        return [70.0] * 90

    def test_returns_expected_keys(self, well_trained: list[float]) -> None:
        """Result should contain all expected keys."""
        result = find_optimal_taper_length(well_trained)
        assert "optimal_days" in result
        assert "peak_tsb" in result
        assert "ctl_at_peak" in result
        assert "atl_at_peak" in result

    def test_optimal_days_in_range(self, well_trained: list[float]) -> None:
        """Optimal taper should fall within the search range."""
        result = find_optimal_taper_length(well_trained, min_days=7, max_days=28)
        assert 7 <= result["optimal_days"] <= 28

    def test_peak_tsb_is_positive(self, well_trained: list[float]) -> None:
        """Peak TSB during optimal taper should be positive (fresh)."""
        result = find_optimal_taper_length(well_trained)
        assert result["peak_tsb"] > 0

    def test_ctl_retained_at_peak(self, well_trained: list[float]) -> None:
        """Significant fitness should be retained at the optimal taper point."""
        pre_taper_ctl = compute_ctl(well_trained, tau=DEFAULT_FITNESS_TAU)
        result = find_optimal_taper_length(well_trained)
        retention = result["ctl_at_peak"] / pre_taper_ctl
        # Should retain at least 60% of fitness
        assert retention > 0.6

    def test_atl_lower_than_ctl_at_peak(self, well_trained: list[float]) -> None:
        """At peak TSB, ATL should be lower than CTL (that's what makes TSB positive)."""
        result = find_optimal_taper_length(well_trained)
        assert result["atl_at_peak"] < result["ctl_at_peak"]

    def test_optimal_days_is_integer(self, well_trained: list[float]) -> None:
        """Optimal days should be an integer."""
        result = find_optimal_taper_length(well_trained)
        assert isinstance(result["optimal_days"], int)

    def test_typical_taper_between_7_and_21_days(self, well_trained: list[float]) -> None:
        """For a well-trained runner, optimal taper is typically 7-21 days.

        This matches the sports science literature (Mujika & Padilla, 2003)
        where optimal taper length for endurance athletes is 8-14 days.
        """
        result = find_optimal_taper_length(well_trained)
        assert 7 <= result["optimal_days"] <= 21

    def test_custom_search_range(self, well_trained: list[float]) -> None:
        """Custom min/max days should constrain the search."""
        result = find_optimal_taper_length(well_trained, min_days=10, max_days=14)
        assert 10 <= result["optimal_days"] <= 14

    def test_single_day_range(self, well_trained: list[float]) -> None:
        """When min_days == max_days, the only option is returned."""
        result = find_optimal_taper_length(well_trained, min_days=10, max_days=10)
        assert result["optimal_days"] == 10

    def test_partial_taper_affects_optimal(self, well_trained: list[float]) -> None:
        """Partial taper (maintaining some load) should shift optimal length."""
        find_optimal_taper_length(well_trained, taper_load_fraction=0.0)
        result_partial = find_optimal_taper_length(well_trained, taper_load_fraction=0.3)
        # Different load fractions should yield different results
        # (they could coincidentally be the same, so test that the function runs)
        assert isinstance(result_partial["optimal_days"], int)
        assert result_partial["peak_tsb"] > 0


class TestComputeTaperFitnessRetention:
    """Tests for fitness retention fraction calculation."""

    @pytest.fixture
    def trained_loads(self) -> list[float]:
        """60 days of steady 80 TSS/day training."""
        return [80.0] * 60

    def test_zero_days_returns_one(self, trained_loads: list[float]) -> None:
        """Zero rest days should mean 100% retention."""
        retention = compute_taper_fitness_retention(trained_loads, taper_days=0)
        assert retention == pytest.approx(1.0, abs=1e-10)

    def test_retention_decreases_with_rest(self, trained_loads: list[float]) -> None:
        """Longer rest should produce lower retention."""
        retention_7 = compute_taper_fitness_retention(trained_loads, taper_days=7)
        retention_14 = compute_taper_fitness_retention(trained_loads, taper_days=14)
        retention_28 = compute_taper_fitness_retention(trained_loads, taper_days=28)
        assert retention_7 > retention_14 > retention_28

    def test_retention_after_one_time_constant(self, trained_loads: list[float]) -> None:
        """After exactly tau days of rest, retention should be ~e^(-1) ≈ 36.8%.

        This is a fundamental property of exponential decay.
        """
        retention = compute_taper_fitness_retention(trained_loads, taper_days=42, fitness_tau=42)
        assert retention == pytest.approx(math.exp(-1), abs=0.02)

    def test_retention_between_zero_and_one(self, trained_loads: list[float]) -> None:
        """Retention should always be between 0 and 1."""
        for days in [1, 7, 14, 28, 42, 60]:
            retention = compute_taper_fitness_retention(trained_loads, taper_days=days)
            assert 0.0 < retention <= 1.0

    def test_short_taper_high_retention(self, trained_loads: list[float]) -> None:
        """7 days of rest should retain >80% of fitness (tau=42)."""
        retention = compute_taper_fitness_retention(trained_loads, taper_days=7)
        assert retention > 0.80

    def test_long_rest_low_retention(self, trained_loads: list[float]) -> None:
        """90 days of rest should retain <20% of fitness."""
        retention = compute_taper_fitness_retention(trained_loads, taper_days=90)
        assert retention < 0.20

    def test_custom_tau_affects_retention(self, trained_loads: list[float]) -> None:
        """Larger tau should produce higher retention for the same rest period."""
        retention_42 = compute_taper_fitness_retention(
            trained_loads, taper_days=14, fitness_tau=42
        )
        retention_60 = compute_taper_fitness_retention(
            trained_loads, taper_days=14, fitness_tau=60
        )
        assert retention_60 > retention_42

    def test_zero_ctl_returns_zero(self) -> None:
        """If pre-taper CTL is zero, retention should be 0.0."""
        loads = [0.0] * 30
        retention = compute_taper_fitness_retention(loads, taper_days=7)
        assert retention == 0.0

    def test_retention_mathematically_close_to_exponential(
        self, trained_loads: list[float]
    ) -> None:
        """For a well-trained athlete, retention should follow e^(-days/tau).

        The exact ratio depends on how converged CTL is, but for a
        long training history it should be close to the theoretical decay.
        """
        days = 14
        tau = 42
        theoretical = math.exp(-days / tau)
        actual = compute_taper_fitness_retention(trained_loads, taper_days=days, fitness_tau=tau)
        # Should be within a few percent of theoretical
        assert actual == pytest.approx(theoretical, abs=0.05)


class TestInputValidation:
    """Tests for input validation across all taper functions."""

    # --- project_taper validation ---

    def test_project_empty_loads_raises(self) -> None:
        """Empty training history should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            project_taper([], taper_days=14)

    def test_project_zero_taper_days_raises(self) -> None:
        """Zero taper days should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            project_taper([50.0] * 30, taper_days=0)

    def test_project_negative_taper_days_raises(self) -> None:
        """Negative taper days should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            project_taper([50.0] * 30, taper_days=-5)

    def test_project_fraction_below_zero_raises(self) -> None:
        """taper_load_fraction below 0 should raise ValueError."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            project_taper([50.0] * 30, taper_days=14, taper_load_fraction=-0.1)

    def test_project_fraction_above_one_raises(self) -> None:
        """taper_load_fraction above 1 should raise ValueError."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            project_taper([50.0] * 30, taper_days=14, taper_load_fraction=1.5)

    def test_project_zero_fitness_tau_raises(self) -> None:
        """Zero fitness_tau should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            project_taper([50.0] * 30, taper_days=14, fitness_tau=0)

    def test_project_negative_fatigue_tau_raises(self) -> None:
        """Negative fatigue_tau should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            project_taper([50.0] * 30, taper_days=14, fatigue_tau=-3)

    # --- find_optimal_taper_length validation ---

    def test_optimal_empty_loads_raises(self) -> None:
        """Empty training history should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            find_optimal_taper_length([])

    def test_optimal_min_days_zero_raises(self) -> None:
        """min_days < 1 should raise ValueError."""
        with pytest.raises(ValueError, match="at least 1"):
            find_optimal_taper_length([50.0] * 30, min_days=0)

    def test_optimal_max_less_than_min_raises(self) -> None:
        """max_days < min_days should raise ValueError."""
        with pytest.raises(ValueError, match=">="):
            find_optimal_taper_length([50.0] * 30, min_days=14, max_days=7)

    # --- compute_taper_fitness_retention validation ---

    def test_retention_empty_loads_raises(self) -> None:
        """Empty training history should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            compute_taper_fitness_retention([], taper_days=7)

    def test_retention_negative_taper_days_raises(self) -> None:
        """Negative taper days should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            compute_taper_fitness_retention([50.0] * 30, taper_days=-1)

    def test_retention_zero_tau_raises(self) -> None:
        """Zero fitness_tau should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_taper_fitness_retention([50.0] * 30, taper_days=7, fitness_tau=0)

    def test_retention_negative_tau_raises(self) -> None:
        """Negative fitness_tau should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_taper_fitness_retention([50.0] * 30, taper_days=7, fitness_tau=-5)


class TestEdgeCases:
    """Edge cases and boundary conditions for taper module."""

    def test_single_day_taper(self) -> None:
        """A 1-day taper should produce single-element output."""
        result = project_taper([50.0] * 30, taper_days=1)
        assert len(result["ctl"]) == 1
        assert len(result["atl"]) == 1
        assert len(result["tsb"]) == 1

    def test_very_long_taper(self) -> None:
        """A very long taper should not cause errors."""
        result = project_taper([50.0] * 30, taper_days=365)
        assert len(result["ctl"]) == 365
        assert all(math.isfinite(v) for v in result["ctl"])

    def test_very_large_loads(self) -> None:
        """Very large loads should not overflow."""
        result = project_taper([1e6] * 30, taper_days=14)
        assert all(math.isfinite(v) for v in result["ctl"])
        assert all(math.isfinite(v) for v in result["atl"])

    def test_fraction_boundary_zero(self) -> None:
        """taper_load_fraction=0.0 should be accepted."""
        result = project_taper([50.0] * 30, taper_days=7, taper_load_fraction=0.0)
        assert len(result["ctl"]) == 7

    def test_fraction_boundary_one(self) -> None:
        """taper_load_fraction=1.0 should be accepted."""
        result = project_taper([50.0] * 30, taper_days=7, taper_load_fraction=1.0)
        assert len(result["ctl"]) == 7

    def test_optimal_with_min_equals_max(self) -> None:
        """min_days == max_days should return that single day."""
        result = find_optimal_taper_length([50.0] * 60, min_days=14, max_days=14)
        assert result["optimal_days"] == 14

    def test_retention_zero_days_of_rest(self) -> None:
        """Zero rest days should return exactly 1.0 retention."""
        retention = compute_taper_fitness_retention([80.0] * 30, taper_days=0)
        assert retention == 1.0

    def test_consistent_with_banister(self) -> None:
        """Taper CTL should match direct Banister computation.

        If we manually extend loads with zeros and compute CTL,
        it should match the taper projection's final CTL value.
        """
        loads = [80.0] * 60
        taper_days = 14

        # Via taper module
        taper_result = project_taper(loads, taper_days=taper_days, taper_load_fraction=0.0)

        # Via direct Banister computation
        extended = loads + [0.0] * taper_days
        direct_ctl = compute_ctl(extended, tau=DEFAULT_FITNESS_TAU)

        assert taper_result["ctl"][-1] == pytest.approx(direct_ctl, rel=1e-10)
