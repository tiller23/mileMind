"""Acute-to-Chronic Workload Ratio (ACWR) Model.

Implements ACWR calculations for monitoring training load progression and
injury risk. Provides both rolling average and exponentially weighted moving
average (EWMA) variants, along with safety zone classification and weekly
mileage increase validation.

The ACWR is the ratio of recent (acute) training load to longer-term
(chronic) training load. Values in the 0.8-1.3 range are generally
considered safe ("sweet spot"), while values above 1.5 represent high
injury risk and are hard-capped by this system regardless of athlete
preference.

References:
    - Gabbett (2016): "The training-injury prevention paradox"
    - Hulin et al. (2014): "The acute:chronic workload ratio predicts injury"
    - Williams et al. (2017): "Better way to determine ACWR" (EWMA)
    - ale-uy/Acute_Chronic_Workload_Ratio (Python reference)

Zones:
    - Safe:    0.8 <= ACWR <= 1.3
    - Warning: 1.3 <  ACWR <= 1.5
    - Danger:  ACWR > 1.5  (hard cap, always rejected)
    - Low:     ACWR < 0.8  (under-training / detraining risk)
"""

import math
from dataclasses import dataclass, field

# --- Constants ---

SAFE_LOWER = 0.8
SAFE_UPPER = 1.3
WARNING_UPPER = 1.5  # Hard cap — system rejects regardless of preference

DEFAULT_ACUTE_DAYS = 7
DEFAULT_CHRONIC_DAYS = 28

DEFAULT_MAX_WEEKLY_INCREASE_PCT = 0.10  # 10% rule
MAX_ALLOWED_WEEKLY_INCREASE_PCT = 0.20  # Hard ceiling even for aggressive

SPIKE_THRESHOLD_PCT = 0.40  # 40% single-week spike flagged per PRD

# Risk tolerance presets: maps tolerance name to the ACWR ceiling that
# triggers a violation. The hard cap at 1.5 is *always* enforced on top.
RISK_TOLERANCE_PRESETS: dict[str, float] = {
    "conservative": 1.2,
    "moderate": 1.3,
    "aggressive": 1.5,
}


@dataclass(frozen=True)
class SafetyResult:
    """Result of a training load safety check.

    Attributes:
        safe: True if no violations were found.
        acwr: The computed ACWR value (rolling variant).
        acwr_ewma: The computed ACWR value (EWMA variant), or None if
            insufficient data.
        zone: One of "low", "safe", "warning", "danger".
        violations: List of human-readable violation descriptions.
    """

    safe: bool
    acwr: float
    acwr_ewma: float | None
    zone: str
    violations: list[str] = field(default_factory=list)


# --- Public functions ---


def compute_acwr_rolling(
    daily_loads: list[float],
    acute_days: int = DEFAULT_ACUTE_DAYS,
    chronic_days: int = DEFAULT_CHRONIC_DAYS,
) -> float:
    """Compute ACWR using a simple rolling average ratio.

    The acute load is the mean daily load over the most recent `acute_days`,
    and the chronic load is the mean daily load over the most recent
    `chronic_days`. ACWR = acute_mean / chronic_mean.

    Args:
        daily_loads: Ordered list of daily training loads (index 0 is oldest,
            index -1 is most recent). Must contain at least `chronic_days`
            entries.
        acute_days: Number of recent days for the acute window. Default 7.
        chronic_days: Number of recent days for the chronic window. Default 28.

    Returns:
        The rolling ACWR value.

    Raises:
        ValueError: If daily_loads has fewer entries than chronic_days,
            if acute_days or chronic_days are not positive, or if
            acute_days >= chronic_days.
    """
    _validate_acwr_inputs(daily_loads, acute_days, chronic_days)

    acute_window = daily_loads[-acute_days:]
    chronic_window = daily_loads[-chronic_days:]

    acute_mean = sum(acute_window) / len(acute_window)
    chronic_mean = sum(chronic_window) / len(chronic_window)

    if chronic_mean == 0.0:
        if acute_mean == 0.0:
            return 0.0
        return math.inf

    return acute_mean / chronic_mean


def compute_acwr_ewma(
    daily_loads: list[float],
    acute_days: int = DEFAULT_ACUTE_DAYS,
    chronic_days: int = DEFAULT_CHRONIC_DAYS,
) -> float:
    """Compute ACWR using Exponentially Weighted Moving Averages.

    The EWMA variant gives more weight to recent loads and is considered
    a more sensitive predictor of injury risk than the rolling average
    (Williams et al., 2017).

    The decay constant for each window is: alpha = 2 / (N + 1), matching
    the standard EWMA definition used in the sports science literature.

    Args:
        daily_loads: Ordered list of daily training loads (index 0 is oldest,
            index -1 is most recent). Must contain at least `chronic_days`
            entries.
        acute_days: Number of days defining the acute EWMA span. Default 7.
        chronic_days: Number of days defining the chronic EWMA span. Default 28.

    Returns:
        The EWMA-based ACWR value.

    Raises:
        ValueError: If daily_loads has fewer entries than chronic_days,
            if acute_days or chronic_days are not positive, or if
            acute_days >= chronic_days.
    """
    _validate_acwr_inputs(daily_loads, acute_days, chronic_days)

    acute_ewma = _compute_ewma(daily_loads, acute_days)
    chronic_ewma = _compute_ewma(daily_loads, chronic_days)

    if chronic_ewma == 0.0:
        if acute_ewma == 0.0:
            return 0.0
        return math.inf

    return acute_ewma / chronic_ewma


def classify_zone(acwr: float) -> str:
    """Classify an ACWR value into a risk zone.

    Args:
        acwr: The ACWR value to classify.

    Returns:
        One of "low", "safe", "warning", or "danger".
    """
    if acwr < SAFE_LOWER:
        return "low"
    if acwr <= SAFE_UPPER:
        return "safe"
    if acwr <= WARNING_UPPER:
        return "warning"
    return "danger"


def check_safety(
    weekly_loads: list[float],
    risk_tolerance: str = "moderate",
    max_weekly_increase_pct: float = DEFAULT_MAX_WEEKLY_INCREASE_PCT,
) -> SafetyResult:
    """Run a comprehensive safety check on weekly training loads.

    Evaluates ACWR (both rolling and EWMA), weekly mileage increase rate,
    and spike detection. Returns a structured result indicating whether
    the progression is safe, the computed ACWR, the risk zone, and a list
    of any violations found.

    The hard cap at ACWR 1.5 is always enforced regardless of risk_tolerance.

    Args:
        weekly_loads: Ordered list of weekly total training loads. Index 0
            is the oldest week, index -1 is the most recent. Must have at
            least 4 entries (to fill the 28-day chronic window).
        risk_tolerance: One of "conservative", "moderate", or "aggressive".
            Controls the ACWR ceiling below the hard cap. Default "moderate".
        max_weekly_increase_pct: Maximum allowed week-over-week load increase
            as a fraction (0.10 = 10%). Default 0.10, hard-capped at 0.20.

    Returns:
        A SafetyResult dataclass with safety status, ACWR value, zone, and
        any violations.

    Raises:
        ValueError: If weekly_loads has fewer than 4 entries, if
            risk_tolerance is not a recognized preset, or if
            max_weekly_increase_pct is not in (0, MAX_ALLOWED_WEEKLY_INCREASE_PCT].
    """
    _validate_safety_inputs(weekly_loads, risk_tolerance, max_weekly_increase_pct)

    # Expand weekly loads to daily loads (constant daily load within each week)
    daily_loads = _weekly_to_daily(weekly_loads)

    violations: list[str] = []

    # --- Compute ACWR (rolling) ---
    acwr_rolling = compute_acwr_rolling(daily_loads, DEFAULT_ACUTE_DAYS, DEFAULT_CHRONIC_DAYS)

    # --- Compute ACWR (EWMA) ---
    acwr_ewma = compute_acwr_ewma(daily_loads, DEFAULT_ACUTE_DAYS, DEFAULT_CHRONIC_DAYS)

    # --- Zone classification (use rolling as primary) ---
    zone = classify_zone(acwr_rolling)

    # --- Hard cap check (ACWR > 1.5, always enforced) ---
    if acwr_rolling > WARNING_UPPER:
        violations.append(
            f"ACWR {acwr_rolling:.2f} exceeds hard cap {WARNING_UPPER:.1f}"
        )
    if acwr_ewma is not None and acwr_ewma > WARNING_UPPER:
        violations.append(
            f"ACWR (EWMA) {acwr_ewma:.2f} exceeds hard cap {WARNING_UPPER:.1f}"
        )

    # --- Risk-tolerance ceiling check ---
    tolerance_ceiling = RISK_TOLERANCE_PRESETS[risk_tolerance]
    if acwr_rolling > tolerance_ceiling and acwr_rolling <= WARNING_UPPER:
        violations.append(
            f"ACWR {acwr_rolling:.2f} exceeds {risk_tolerance} ceiling "
            f"{tolerance_ceiling:.1f}"
        )

    # --- Weekly mileage increase check ---
    capped_pct = min(max_weekly_increase_pct, MAX_ALLOWED_WEEKLY_INCREASE_PCT)
    for i in range(1, len(weekly_loads)):
        prev = weekly_loads[i - 1]
        curr = weekly_loads[i]
        if prev > 0:
            increase = (curr - prev) / prev
            if increase > capped_pct:
                violations.append(
                    f"Week {i + 1} increase {increase:.0%} exceeds "
                    f"limit {capped_pct:.0%} (from {prev:.1f} to {curr:.1f})"
                )

    # --- Spike detection (40% single-week increase per PRD) ---
    for i in range(1, len(weekly_loads)):
        prev = weekly_loads[i - 1]
        curr = weekly_loads[i]
        if prev > 0:
            increase = (curr - prev) / prev
            if increase >= SPIKE_THRESHOLD_PCT:
                violations.append(
                    f"Load spike in week {i + 1}: {increase:.0%} increase "
                    f"(threshold {SPIKE_THRESHOLD_PCT:.0%})"
                )

    safe = len(violations) == 0
    return SafetyResult(
        safe=safe,
        acwr=acwr_rolling,
        acwr_ewma=acwr_ewma,
        zone=zone,
        violations=violations,
    )


def validate_weekly_increase(
    previous_week: float,
    proposed_week: float,
    max_increase_pct: float = DEFAULT_MAX_WEEKLY_INCREASE_PCT,
) -> tuple[bool, float]:
    """Check whether a proposed weekly load violates the increase limit.

    Args:
        previous_week: Total load for the previous week.
        proposed_week: Total load for the upcoming week.
        max_increase_pct: Maximum allowed fractional increase (0.10 = 10%).
            Clamped to MAX_ALLOWED_WEEKLY_INCREASE_PCT (20%).

    Returns:
        A tuple of (is_valid, actual_increase_pct). is_valid is True if
        the increase is within limits.

    Raises:
        ValueError: If previous_week is negative, or if max_increase_pct
            is not positive.
    """
    if previous_week < 0:
        raise ValueError(f"previous_week must be non-negative, got {previous_week}")
    if max_increase_pct <= 0:
        raise ValueError(f"max_increase_pct must be positive, got {max_increase_pct}")

    capped_pct = min(max_increase_pct, MAX_ALLOWED_WEEKLY_INCREASE_PCT)

    if previous_week == 0.0:
        return (True, 0.0)

    increase = (proposed_week - previous_week) / previous_week
    return (increase <= capped_pct, increase)


# --- Private helpers ---


def _compute_ewma(daily_loads: list[float], span: int) -> float:
    """Compute the final EWMA value for a daily load series.

    Args:
        daily_loads: Daily training loads.
        span: The span (window size) for the EWMA.

    Returns:
        Final EWMA value.
    """
    alpha = 2.0 / (span + 1)
    ewma = daily_loads[0]
    for load in daily_loads[1:]:
        ewma = alpha * load + (1.0 - alpha) * ewma
    return ewma


def _weekly_to_daily(weekly_loads: list[float]) -> list[float]:
    """Convert weekly totals to daily loads (uniform within each week).

    Args:
        weekly_loads: List of weekly total loads.

    Returns:
        List of daily loads (length = len(weekly_loads) * 7).
    """
    daily: list[float] = []
    for week_total in weekly_loads:
        daily_load = week_total / 7.0
        daily.extend([daily_load] * 7)
    return daily


def _validate_acwr_inputs(
    daily_loads: list[float],
    acute_days: int,
    chronic_days: int,
) -> None:
    """Validate inputs for ACWR computation functions.

    Args:
        daily_loads: Must have at least chronic_days entries.
        acute_days: Must be positive.
        chronic_days: Must be positive and greater than acute_days.

    Raises:
        ValueError: On invalid inputs.
    """
    if acute_days <= 0:
        raise ValueError(f"acute_days must be positive, got {acute_days}")
    if chronic_days <= 0:
        raise ValueError(f"chronic_days must be positive, got {chronic_days}")
    if acute_days >= chronic_days:
        raise ValueError(
            f"acute_days ({acute_days}) must be less than "
            f"chronic_days ({chronic_days})"
        )
    if len(daily_loads) < chronic_days:
        raise ValueError(
            f"daily_loads must have at least {chronic_days} entries, "
            f"got {len(daily_loads)}"
        )


def _validate_safety_inputs(
    weekly_loads: list[float],
    risk_tolerance: str,
    max_weekly_increase_pct: float,
) -> None:
    """Validate inputs for check_safety().

    Args:
        weekly_loads: Must have at least 4 entries (28 days for chronic window).
        risk_tolerance: Must be a recognized preset name.
        max_weekly_increase_pct: Must be positive and <= MAX_ALLOWED_WEEKLY_INCREASE_PCT.

    Raises:
        ValueError: On invalid inputs.
    """
    if len(weekly_loads) < 4:
        raise ValueError(
            f"weekly_loads must have at least 4 entries, got {len(weekly_loads)}"
        )
    if risk_tolerance not in RISK_TOLERANCE_PRESETS:
        raise ValueError(
            f"risk_tolerance must be one of {list(RISK_TOLERANCE_PRESETS.keys())}, "
            f"got '{risk_tolerance}'"
        )
    if max_weekly_increase_pct <= 0:
        raise ValueError(
            f"max_weekly_increase_pct must be positive, got {max_weekly_increase_pct}"
        )
    if max_weekly_increase_pct > MAX_ALLOWED_WEEKLY_INCREASE_PCT:
        raise ValueError(
            f"max_weekly_increase_pct must be at most {MAX_ALLOWED_WEEKLY_INCREASE_PCT}, "
            f"got {max_weekly_increase_pct}"
        )
