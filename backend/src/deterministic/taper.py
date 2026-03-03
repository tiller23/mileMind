"""Taper Decay Modeling.

Models fitness retention and fatigue dissipation during pre-race taper
periods. Built on top of the Banister impulse-response model by projecting
CTL/ATL/TSB curves forward with reduced (or zero) training load.

The key insight: during a taper, load drops to zero (or near-zero), so
fitness (CTL, τ=42) decays slowly while fatigue (ATL, τ=7) decays quickly.
This creates a positive TSB window — the athlete becomes "fresh" while
retaining most of their fitness. Finding the optimal taper length means
finding the day where TSB peaks before too much fitness erodes.

References:
    - Banister et al. (1975): Impulse-response model
    - Thomas & Busso (2005): Taper optimization in endurance sports
    - Mujika & Padilla (2003): "Scientific bases for precompetition tapering"
    - PRD Section 5.2: "Built naturally into the Banister impulse-response
      model by setting future training impulse to zero"
"""

from src.deterministic.banister import (
    DEFAULT_FATIGUE_TAU,
    DEFAULT_FITNESS_TAU,
    compute_atl,
    compute_ctl,
    compute_ema_series,
)


def project_taper(
    daily_loads: list[float],
    taper_days: int,
    taper_load_fraction: float = 0.0,
    fitness_tau: int = DEFAULT_FITNESS_TAU,
    fatigue_tau: int = DEFAULT_FATIGUE_TAU,
) -> dict[str, list[float]]:
    """Project CTL, ATL, and TSB forward during a taper period.

    Extends the athlete's training history with `taper_days` of reduced
    load, then computes the CTL/ATL/TSB curves for the taper period only.

    Args:
        daily_loads: Existing training history (daily TSS values).
            Index 0 is oldest, index -1 is most recent.
        taper_days: Number of days to project forward.
        taper_load_fraction: Fraction of recent average load to maintain
            during the taper. 0.0 = complete rest, 0.3 = 30% of recent
            average. Must be in [0.0, 1.0].
        fitness_tau: Time constant for CTL. Default 42 days.
        fatigue_tau: Time constant for ATL. Default 7 days.

    Returns:
        Dict with keys "ctl", "atl", "tsb", each a list of floats
        covering only the taper period (length = taper_days).

    Raises:
        ValueError: If daily_loads is empty, taper_days is not positive,
            taper_load_fraction is outside [0, 1], or tau values are
            not positive.
    """
    _validate_taper_inputs(daily_loads, taper_days, taper_load_fraction)
    if fitness_tau <= 0:
        raise ValueError(f"fitness_tau must be positive, got {fitness_tau}")
    if fatigue_tau <= 0:
        raise ValueError(f"fatigue_tau must be positive, got {fatigue_tau}")

    # Compute taper daily load from recent training average
    recent_window = min(14, len(daily_loads))
    recent_avg = sum(daily_loads[-recent_window:]) / recent_window
    taper_load = recent_avg * taper_load_fraction

    # Build extended load series: full history + taper period
    extended_loads = daily_loads + [taper_load] * taper_days

    # Compute full series, then slice out just the taper portion
    ctl_full = compute_ema_series(extended_loads, fitness_tau)
    atl_full = compute_ema_series(extended_loads, fatigue_tau)

    start = len(daily_loads)
    ctl_taper = ctl_full[start:]
    atl_taper = atl_full[start:]
    tsb_taper = [c - a for c, a in zip(ctl_taper, atl_taper)]

    return {"ctl": ctl_taper, "atl": atl_taper, "tsb": tsb_taper}


def find_optimal_taper_length(
    daily_loads: list[float],
    min_days: int = 7,
    max_days: int = 28,
    taper_load_fraction: float = 0.0,
    fitness_tau: int = DEFAULT_FITNESS_TAU,
    fatigue_tau: int = DEFAULT_FATIGUE_TAU,
) -> dict[str, float | int]:
    """Find the taper duration that maximizes TSB (peak freshness).

    Simulates tapers from min_days to max_days and returns the length
    that produces the highest Training Stress Balance.

    Args:
        daily_loads: Existing training history (daily TSS values).
        min_days: Minimum taper length to consider. Default 7.
        max_days: Maximum taper length to consider. Default 28.
        taper_load_fraction: Fraction of load maintained during taper.
        fitness_tau: Time constant for CTL. Default 42 days.
        fatigue_tau: Time constant for ATL. Default 7 days.

    Returns:
        Dict with keys:
            "optimal_days": int — best taper length
            "peak_tsb": float — TSB at the optimal day
            "ctl_at_peak": float — CTL at the optimal day
            "atl_at_peak": float — ATL at the optimal day

    Raises:
        ValueError: If daily_loads is empty, min_days < 1, max_days < min_days,
            or other inputs are invalid.
    """
    if not daily_loads:
        raise ValueError("daily_loads must be non-empty")
    if min_days < 1:
        raise ValueError(f"min_days must be at least 1, got {min_days}")
    if max_days < min_days:
        raise ValueError(
            f"max_days ({max_days}) must be >= min_days ({min_days})"
        )

    # Project the full max_days taper
    result = project_taper(
        daily_loads, max_days, taper_load_fraction, fitness_tau, fatigue_tau
    )

    # Search for peak TSB within [min_days, max_days]
    best_day = min_days
    best_tsb = result["tsb"][min_days - 1]
    for day in range(min_days, max_days + 1):
        tsb = result["tsb"][day - 1]  # day is 1-indexed, list is 0-indexed
        if tsb > best_tsb:
            best_tsb = tsb
            best_day = day

    return {
        "optimal_days": best_day,
        "peak_tsb": best_tsb,
        "ctl_at_peak": result["ctl"][best_day - 1],
        "atl_at_peak": result["atl"][best_day - 1],
    }


def compute_taper_fitness_retention(
    daily_loads: list[float],
    taper_days: int,
    fitness_tau: int = DEFAULT_FITNESS_TAU,
) -> float:
    """Calculate what fraction of fitness is retained after a taper.

    Computes CTL before the taper and after `taper_days` of complete
    rest, returning the ratio.

    Args:
        daily_loads: Existing training history (daily TSS values).
        taper_days: Number of rest days to simulate.
        fitness_tau: Time constant for CTL. Default 42 days.

    Returns:
        Fitness retention as a fraction (e.g., 0.85 = 85% retained).
        Returns 0.0 if pre-taper CTL is zero.

    Raises:
        ValueError: If daily_loads is empty, taper_days is negative,
            or fitness_tau is not positive.
    """
    if not daily_loads:
        raise ValueError("daily_loads must be non-empty")
    if taper_days < 0:
        raise ValueError(f"taper_days must be non-negative, got {taper_days}")
    if fitness_tau <= 0:
        raise ValueError(f"fitness_tau must be positive, got {fitness_tau}")

    pre_taper_ctl = compute_ctl(daily_loads, tau=fitness_tau)

    if pre_taper_ctl == 0.0:
        return 0.0

    if taper_days == 0:
        return 1.0

    # Extend with complete rest
    extended = daily_loads + [0.0] * taper_days
    post_taper_ctl = compute_ctl(extended, tau=fitness_tau)

    return post_taper_ctl / pre_taper_ctl


def _validate_taper_inputs(
    daily_loads: list[float],
    taper_days: int,
    taper_load_fraction: float,
) -> None:
    """Validate common inputs for taper functions.

    Args:
        daily_loads: Must be non-empty.
        taper_days: Must be positive.
        taper_load_fraction: Must be in [0.0, 1.0].

    Raises:
        ValueError: On invalid inputs.
    """
    if not daily_loads:
        raise ValueError("daily_loads must be non-empty")
    if taper_days <= 0:
        raise ValueError(f"taper_days must be positive, got {taper_days}")
    if not 0.0 <= taper_load_fraction <= 1.0:
        raise ValueError(
            f"taper_load_fraction must be between 0 and 1, got {taper_load_fraction}"
        )
