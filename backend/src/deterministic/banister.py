"""Banister Impulse-Response (Fitness-Fatigue) Model.

Implements the Banister impulse-response model for tracking cumulative training
load and recovery. Computes CTL (chronic training load / fitness), ATL (acute
training load / fatigue), and TSB (training stress balance / form) using
exponential moving averages with configurable time constants.

References:
    - Banister et al. (1975): "A systems model of training for athletic performance"
    - GoldenCheetah (C++): PMC chart implementation
    - choochoo SHRIMP: Python Banister variant

The EMA recurrence for a daily load series w_1, w_2, ..., w_n is:
    EMA_0 = 0
    EMA_i = EMA_{i-1} * e^(-1/τ) + w_i * (1 - e^(-1/τ))

This is equivalent to an exponentially weighted average where each day's
contribution decays as e^(-t/τ) over time.
"""

import math
from typing import Literal

__all__ = [
    "DEFAULT_FATIGUE_TAU",
    "DEFAULT_FITNESS_TAU",
    "RecoveryStatus",
    "classify_recovery_status",
    "compute_atl",
    "compute_ctl",
    "compute_ema_series",
    "compute_tsb",
    "compute_tsb_series",
]

# Default time constants from exercise science literature
DEFAULT_FITNESS_TAU = 42  # days — chronic training load decay
DEFAULT_FATIGUE_TAU = 7  # days — acute training load decay

# TSB classification thresholds (Coggan/Allen Performance Manager)
_TSB_FRESH_THRESHOLD = 10.0
_TSB_FATIGUED_THRESHOLD = -10.0
_TSB_VERY_FATIGUED_THRESHOLD = -20.0

RecoveryStatus = Literal["fresh", "neutral", "fatigued", "very_fatigued"]


def compute_ctl(
    daily_loads: list[float],
    tau: int = DEFAULT_FITNESS_TAU,
    initial_ctl: float = 0.0,
) -> float:
    """Compute Chronic Training Load (fitness) from daily training stress values.

    Uses an exponential moving average with time constant τ (default 42 days)
    to model the slow-adapting fitness response to training.

    Args:
        daily_loads: Ordered list of daily training stress scores (e.g., TSS).
            Index 0 is the oldest day, index -1 is the most recent.
        tau: Time constant in days for fitness decay. Higher values mean
            slower adaptation. Default is 42 days per Banister model.
        initial_ctl: Starting CTL value before the first day. Default 0.0
            assumes no prior training history.

    Returns:
        The CTL value after processing all daily loads.

    Raises:
        ValueError: If daily_loads is empty or tau is not positive.
    """
    _validate_inputs(daily_loads, tau)
    return _compute_ema(daily_loads, tau, initial_ctl)


def compute_atl(
    daily_loads: list[float],
    tau: int = DEFAULT_FATIGUE_TAU,
    initial_atl: float = 0.0,
) -> float:
    """Compute Acute Training Load (fatigue) from daily training stress values.

    Uses an exponential moving average with time constant τ (default 7 days)
    to model the fast-responding fatigue from training.

    Args:
        daily_loads: Ordered list of daily training stress scores (e.g., TSS).
            Index 0 is the oldest day, index -1 is the most recent.
        tau: Time constant in days for fatigue decay. Lower values mean
            faster response. Default is 7 days per Banister model.
        initial_atl: Starting ATL value before the first day. Default 0.0
            assumes no prior training history.

    Returns:
        The ATL value after processing all daily loads.

    Raises:
        ValueError: If daily_loads is empty or tau is not positive.
    """
    _validate_inputs(daily_loads, tau)
    return _compute_ema(daily_loads, tau, initial_atl)


def compute_tsb(
    daily_loads: list[float],
    fitness_tau: int = DEFAULT_FITNESS_TAU,
    fatigue_tau: int = DEFAULT_FATIGUE_TAU,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> float:
    """Compute Training Stress Balance (form) as CTL minus ATL.

    TSB represents the balance between fitness and fatigue. Positive TSB
    indicates freshness (fitness exceeds fatigue), negative indicates
    accumulated fatigue.

    Args:
        daily_loads: Ordered list of daily training stress scores.
        fitness_tau: Time constant for CTL calculation. Default 42 days.
        fatigue_tau: Time constant for ATL calculation. Default 7 days.
        initial_ctl: Starting CTL value. Default 0.0.
        initial_atl: Starting ATL value. Default 0.0.

    Returns:
        TSB value (CTL - ATL) after processing all daily loads.

    Raises:
        ValueError: If daily_loads is empty or either tau is not positive.
    """
    ctl = compute_ctl(daily_loads, fitness_tau, initial_ctl)
    atl = compute_atl(daily_loads, fatigue_tau, initial_atl)
    return ctl - atl


def compute_ema_series(
    daily_loads: list[float],
    tau: int,
    initial_value: float = 0.0,
) -> list[float]:
    """Compute the full EMA series for every day in the load history.

    Useful for charting CTL/ATL/TSB curves over time (e.g., the Training
    Load Chart dashboard component).

    Args:
        daily_loads: Ordered list of daily training stress scores.
        tau: Time constant in days for the exponential decay.
        initial_value: Starting EMA value before the first day. Default 0.0.

    Returns:
        List of EMA values, one per day, same length as daily_loads.

    Raises:
        ValueError: If daily_loads is empty or tau is not positive.
    """
    _validate_inputs(daily_loads, tau)
    decay = math.exp(-1.0 / tau)
    alpha = 1.0 - decay
    series = []
    ema = initial_value
    for load in daily_loads:
        ema = ema * decay + load * alpha
        series.append(ema)
    return series


def compute_tsb_series(
    daily_loads: list[float],
    fitness_tau: int = DEFAULT_FITNESS_TAU,
    fatigue_tau: int = DEFAULT_FATIGUE_TAU,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> dict[str, list[float]]:
    """Compute full CTL, ATL, and TSB series for charting.

    Returns all three curves for the Training Load Chart component.

    Args:
        daily_loads: Ordered list of daily training stress scores.
        fitness_tau: Time constant for CTL. Default 42 days.
        fatigue_tau: Time constant for ATL. Default 7 days.
        initial_ctl: Starting CTL value. Default 0.0.
        initial_atl: Starting ATL value. Default 0.0.

    Returns:
        Dict with keys "ctl", "atl", "tsb", each a list of floats.

    Raises:
        ValueError: If daily_loads is empty or either tau is not positive.
    """
    ctl_series = compute_ema_series(daily_loads, fitness_tau, initial_ctl)
    atl_series = compute_ema_series(daily_loads, fatigue_tau, initial_atl)
    tsb_series = [c - a for c, a in zip(ctl_series, atl_series)]
    return {"ctl": ctl_series, "atl": atl_series, "tsb": tsb_series}


def _compute_ema(
    daily_loads: list[float],
    tau: int,
    initial_value: float,
) -> float:
    """Internal: compute final EMA value from a daily load series.

    Args:
        daily_loads: Daily training stress values.
        tau: Time constant in days.
        initial_value: Starting EMA value.

    Returns:
        Final EMA value after processing all loads.
    """
    decay = math.exp(-1.0 / tau)
    alpha = 1.0 - decay
    ema = initial_value
    for load in daily_loads:
        ema = ema * decay + load * alpha
    return ema


def classify_recovery_status(tsb: float) -> RecoveryStatus:
    """Classify a TSB value into a recovery status category.

    Thresholds follow the Coggan/Allen Performance Manager framework:
        - fresh:          TSB > 10
        - neutral:        -10 <= TSB <= 10
        - fatigued:       -20 <= TSB < -10
        - very_fatigued:  TSB < -20

    Args:
        tsb: Training Stress Balance (CTL - ATL).

    Returns:
        One of "fresh", "neutral", "fatigued", or "very_fatigued".
    """
    if tsb > _TSB_FRESH_THRESHOLD:
        return "fresh"
    if tsb >= _TSB_FATIGUED_THRESHOLD:
        return "neutral"
    if tsb >= _TSB_VERY_FATIGUED_THRESHOLD:
        return "fatigued"
    return "very_fatigued"


def _validate_inputs(daily_loads: list[float], tau: int) -> None:
    """Validate common inputs for Banister model functions.

    Args:
        daily_loads: Must be non-empty.
        tau: Must be a positive integer.

    Raises:
        ValueError: If daily_loads is empty or tau is not positive.
    """
    if not daily_loads:
        raise ValueError("daily_loads must be non-empty")
    if tau <= 0:
        raise ValueError(f"tau must be positive, got {tau}")
