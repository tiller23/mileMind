"""Daniels-Gilbert VO2max, VDOT, and Pace Zone Calculations.

Implements the Daniels-Gilbert oxygen expenditure equations for estimating
aerobic capacity (VDOT) from race performances and deriving training pace
zones. Also includes Karvonen heart rate zone calculations.

The VDOT score is a pseudo-VO2max derived from race performance using two
component equations:
    1. Oxygen cost of running at velocity v (ml O2/kg/min)
    2. Maximum sustainable fraction of VO2max for duration t

References:
    - Daniels & Gilbert (1979): "Oxygen Power: Performance Tables for Distance Runners"
    - Daniels (2005): "Daniels' Running Formula", 2nd Edition, Human Kinetics
    - mekeetsa/vdot: GitHub reference implementation
"""

import math

# -----------------------------------------------------------------------
# Daniels-Gilbert equation coefficients
# -----------------------------------------------------------------------
# Oxygen cost equation: VO2 = _A + _B * v + _C * v^2  (v in m/min)
_VO2_A = -4.60
_VO2_B = 0.182258
_VO2_C = 0.000104

# Drop-dead time equation (sustainable %VO2max):
# %VO2max = _PCT_A + _PCT_B * e^(_PCT_C * t) + _PCT_D * e^(_PCT_E * t)
_PCT_A = 0.8
_PCT_B = 0.1894393
_PCT_C = -0.012778
_PCT_D = 0.2989558
_PCT_E = -0.1932605

# -----------------------------------------------------------------------
# Standard race distances (meters)
# -----------------------------------------------------------------------
RACE_DISTANCES: dict[str, float] = {
    "1500m": 1500.0,
    "mile": 1609.344,
    "3000m": 3000.0,
    "5K": 5000.0,
    "10K": 10000.0,
    "half_marathon": 21097.5,
    "marathon": 42195.0,
}

# -----------------------------------------------------------------------
# Training zones as fractions of VO2max (Daniels' Running Formula)
# -----------------------------------------------------------------------
TRAINING_ZONES: dict[str, tuple[float, float]] = {
    "easy": (0.59, 0.74),
    "marathon": (0.75, 0.84),
    "threshold": (0.83, 0.88),
    "interval": (0.95, 1.00),
    "repetition": (1.05, 1.20),
}

# Karvonen HR zones as fractions of heart rate reserve
HR_ZONES: dict[str, tuple[float, float]] = {
    "easy": (0.60, 0.75),
    "marathon": (0.75, 0.80),
    "threshold": (0.85, 0.90),
    "interval": (0.95, 1.00),
}


def velocity_to_vo2(velocity: float) -> float:
    """Calculate oxygen cost of running at a given velocity.

    Uses the Daniels-Gilbert regression relating running speed to oxygen
    consumption. This is a pure metabolic cost function — it tells you
    how much oxygen a runner consumes at a given pace.

    Args:
        velocity: Running speed in meters per minute.

    Returns:
        Oxygen consumption in ml O2/kg/min.

    Raises:
        ValueError: If velocity is not positive.
    """
    if velocity <= 0:
        raise ValueError(f"velocity must be positive, got {velocity}")
    return _VO2_A + _VO2_B * velocity + _VO2_C * velocity * velocity


def sustained_vo2max_fraction(time_minutes: float) -> float:
    """Calculate the fraction of VO2max sustainable for a given duration.

    Shorter efforts allow higher fractions of VO2max to be sustained.
    A ~5-minute effort uses ~97% VO2max; a marathon uses ~80%.

    Args:
        time_minutes: Duration of the effort in minutes.

    Returns:
        Fraction of VO2max (typically 0.7-1.0 for racing durations).

    Raises:
        ValueError: If time_minutes is not positive.
    """
    if time_minutes <= 0:
        raise ValueError(f"time_minutes must be positive, got {time_minutes}")
    t = time_minutes
    return _PCT_A + _PCT_B * math.exp(_PCT_C * t) + _PCT_D * math.exp(_PCT_E * t)


def compute_vdot(distance_meters: float, time_minutes: float) -> float:
    """Compute VDOT score from a race performance.

    VDOT is the effective VO2max implied by a race result, calculated as
    the oxygen cost at race pace divided by the sustainable fraction of
    VO2max for that duration.

    Args:
        distance_meters: Race distance in meters (e.g., 5000 for a 5K).
        time_minutes: Finish time in minutes (e.g., 20.0 for 20:00).

    Returns:
        VDOT score (dimensionless pseudo-VO2max).

    Raises:
        ValueError: If distance or time is not positive.
    """
    if distance_meters <= 0:
        raise ValueError(f"distance_meters must be positive, got {distance_meters}")
    if time_minutes <= 0:
        raise ValueError(f"time_minutes must be positive, got {time_minutes}")

    velocity = distance_meters / time_minutes
    vo2 = velocity_to_vo2(velocity)
    pct = sustained_vo2max_fraction(time_minutes)
    return vo2 / pct


def vo2_to_velocity(vo2: float) -> float:
    """Solve for velocity given an oxygen consumption rate.

    Inverts the Daniels-Gilbert VO2 equation using the quadratic formula.
    Returns the positive root (the physically meaningful solution).

    Args:
        vo2: Target oxygen consumption in ml O2/kg/min.

    Returns:
        Velocity in meters per minute.

    Raises:
        ValueError: If vo2 is too low to solve (negative discriminant).
    """
    # Solve: _VO2_C * v^2 + _VO2_B * v + (_VO2_A - vo2) = 0
    a = _VO2_C
    b = _VO2_B
    c = _VO2_A - vo2

    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        raise ValueError(f"Cannot solve for velocity: vo2={vo2} produces negative discriminant")

    return (-b + math.sqrt(discriminant)) / (2 * a)


def predict_race_time(vdot: float, distance_meters: float) -> float:
    """Predict race time for a given distance based on VDOT.

    Numerically solves for the time t where:
        velocity_to_vo2(distance/t) / sustained_vo2max_fraction(t) == vdot

    Uses bisection method for robustness.

    Args:
        vdot: Athlete's VDOT score.
        distance_meters: Race distance in meters.

    Returns:
        Predicted finish time in minutes.

    Raises:
        ValueError: If vdot or distance is not positive, or if no solution
            is found within reasonable bounds (3.5 min to 1440 min).
    """
    if vdot <= 0:
        raise ValueError(f"vdot must be positive, got {vdot}")
    if distance_meters <= 0:
        raise ValueError(f"distance_meters must be positive, got {distance_meters}")

    def residual(t: float) -> float:
        v = distance_meters / t
        return velocity_to_vo2(v) / sustained_vo2max_fraction(t) - vdot

    # Bisection search between 3.5 minutes and 24 hours
    lo, hi = 3.5, 1440.0
    if residual(lo) * residual(hi) > 0:
        raise ValueError(
            f"No solution found for vdot={vdot}, distance={distance_meters}m "
            f"in range [{lo}, {hi}] minutes"
        )

    for _ in range(100):  # ~30 iterations needed for <1ms precision
        mid = (lo + hi) / 2
        if residual(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break

    return (lo + hi) / 2


def compute_training_paces(vdot: float) -> dict[str, tuple[float, float]]:
    """Compute training pace zones from a VDOT score.

    Each zone is defined as a range of %VO2max. For each bound, the
    corresponding velocity is calculated and converted to pace in
    seconds per kilometer.

    Args:
        vdot: Athlete's VDOT score.

    Returns:
        Dict mapping zone name to (fast_pace_sec_per_km, slow_pace_sec_per_km).
        Lower values = faster pace. Both bounds are in seconds/km.

    Raises:
        ValueError: If vdot is not positive.
    """
    if vdot <= 0:
        raise ValueError(f"vdot must be positive, got {vdot}")

    paces: dict[str, tuple[float, float]] = {}
    for zone_name, (low_pct, high_pct) in TRAINING_ZONES.items():
        # Higher %VO2max = faster pace = lower sec/km
        fast_vo2 = vdot * high_pct
        slow_vo2 = vdot * low_pct

        fast_velocity = vo2_to_velocity(fast_vo2)
        slow_velocity = vo2_to_velocity(slow_vo2)

        # Convert m/min to sec/km: (1000 m/km) / (v m/min) * (60 sec/min)
        fast_pace = 1000.0 / fast_velocity * 60.0
        slow_pace = 1000.0 / slow_velocity * 60.0

        paces[zone_name] = (fast_pace, slow_pace)

    return paces


def velocity_to_pace_per_km(velocity: float) -> float:
    """Convert velocity in m/min to pace in seconds per kilometer.

    Args:
        velocity: Speed in meters per minute.

    Returns:
        Pace in seconds per kilometer.

    Raises:
        ValueError: If velocity is not positive.
    """
    if velocity <= 0:
        raise ValueError(f"velocity must be positive, got {velocity}")
    return 1000.0 / velocity * 60.0


def velocity_to_pace_per_mile(velocity: float) -> float:
    """Convert velocity in m/min to pace in seconds per mile.

    Args:
        velocity: Speed in meters per minute.

    Returns:
        Pace in seconds per mile.

    Raises:
        ValueError: If velocity is not positive.
    """
    if velocity <= 0:
        raise ValueError(f"velocity must be positive, got {velocity}")
    return 1609.344 / velocity * 60.0


def karvonen_hr(hr_max: int, hr_rest: int, intensity: float) -> int:
    """Calculate target heart rate using the Karvonen formula.

    THR = HRrest + intensity * (HRmax - HRrest)

    This accounts for heart rate reserve (HRR), making it more
    accurate than simple %HRmax methods.

    Args:
        hr_max: Maximum heart rate in bpm.
        hr_rest: Resting heart rate in bpm.
        intensity: Target intensity as a fraction (e.g., 0.70 for 70%).

    Returns:
        Target heart rate in bpm (rounded to nearest integer).

    Raises:
        ValueError: If hr_max <= hr_rest, or intensity is outside [0, 1].
    """
    if hr_max <= hr_rest:
        raise ValueError(f"hr_max ({hr_max}) must be greater than hr_rest ({hr_rest})")
    if not 0.0 <= intensity <= 1.0:
        raise ValueError(f"intensity must be between 0 and 1, got {intensity}")

    return round(hr_rest + intensity * (hr_max - hr_rest))


def compute_hr_zones(hr_max: int, hr_rest: int) -> dict[str, tuple[int, int]]:
    """Compute heart rate training zones using the Karvonen formula.

    Args:
        hr_max: Maximum heart rate in bpm.
        hr_rest: Resting heart rate in bpm.

    Returns:
        Dict mapping zone name to (low_hr, high_hr) in bpm.

    Raises:
        ValueError: If hr_max <= hr_rest.
    """
    if hr_max <= hr_rest:
        raise ValueError(f"hr_max ({hr_max}) must be greater than hr_rest ({hr_rest})")

    zones: dict[str, tuple[int, int]] = {}
    for zone_name, (low_pct, high_pct) in HR_ZONES.items():
        low_hr = karvonen_hr(hr_max, hr_rest, low_pct)
        high_hr = karvonen_hr(hr_max, hr_rest, high_pct)
        zones[zone_name] = (low_hr, high_hr)
    return zones


def estimate_hr_max(age: int, method: str = "tanaka") -> int:
    """Estimate maximum heart rate from age.

    Args:
        age: Athlete's age in years.
        method: Estimation formula to use.
            "fox" — 220 - age (classic, less accurate for older adults)
            "tanaka" — 208 - 0.7 * age (more accurate, recommended)

    Returns:
        Estimated maximum heart rate in bpm.

    Raises:
        ValueError: If age is not positive or method is unknown.
    """
    if age <= 0:
        raise ValueError(f"age must be positive, got {age}")

    if method == "tanaka":
        return round(208 - 0.7 * age)
    elif method == "fox":
        return 220 - age
    else:
        raise ValueError(f"Unknown method '{method}'. Use 'tanaka' or 'fox'.")
