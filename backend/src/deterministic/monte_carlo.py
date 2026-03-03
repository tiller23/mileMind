"""Monte Carlo Race Simulation Engine.

Runs stochastic simulations of race-day performance based on current fitness
state, fatigue levels, and environmental factors. Samples runner paces from
distributions and returns predicted finish-time ranges with confidence
intervals.

The simulation pipeline:
    1. Compute baseline pace from VDOT (Daniels model)
    2. Apply fitness/fatigue adjustment from Banister state (CTL/ATL/TSB)
    3. Per-simulation: sample pace variation from normal distribution
    4. Per-simulation: apply environmental factors (heat, elevation, wind)
    5. Aggregate results into finish-time distribution with percentiles

References:
    - mountain-software-jp/trail-simulator: Python Monte Carlo for trail races
    - Daniels (2005): Pace-VO2 relationship for baseline prediction
    - PRD Section 5.2: "Runs stochastic simulations of race-day performance"
"""

import math
import random
from dataclasses import dataclass

from src.deterministic.daniels import compute_vdot, predict_race_time

# --- Constants ---

DEFAULT_NUM_SIMULATIONS = 10_000
DEFAULT_PACE_CV = 0.03  # 3% coefficient of variation in pace

# Heat penalty: seconds per km slower per degree C above baseline (18C)
HEAT_PENALTY_PER_DEGREE_C = 0.01  # 1% pace penalty per degree above baseline
HEAT_BASELINE_C = 18.0  # Optimal racing temperature

# Elevation gain penalty: % pace penalty per meter of gain per km
ELEVATION_GAIN_PENALTY_PER_M = 0.0005  # 0.05% per meter gain per km

# Wind penalty: % pace penalty per m/s of headwind
HEADWIND_PENALTY_PER_MS = 0.005  # 0.5% per m/s headwind

# TSB-based adjustment: positive TSB = faster, negative = slower
TSB_PACE_ADJUSTMENT_PER_UNIT = 0.001  # 0.1% pace change per TSB point


@dataclass(frozen=True)
class EnvironmentConditions:
    """Environmental conditions affecting race performance.

    Attributes:
        temperature_c: Race-day temperature in Celsius. Optimal is 18C.
            Values above baseline incur a heat penalty.
        elevation_gain_m: Total course elevation gain in meters.
            More gain = slower pace.
        headwind_ms: Average headwind in meters/second.
            Positive = headwind (slower), negative = tailwind (faster).
    """

    temperature_c: float = HEAT_BASELINE_C
    elevation_gain_m: float = 0.0
    headwind_ms: float = 0.0


@dataclass(frozen=True)
class SimulationResult:
    """Result of a Monte Carlo race simulation.

    Attributes:
        median_time_minutes: Median predicted finish time.
        mean_time_minutes: Mean predicted finish time.
        std_time_minutes: Standard deviation of finish times.
        p5_time_minutes: 5th percentile (optimistic bound).
        p25_time_minutes: 25th percentile.
        p75_time_minutes: 75th percentile.
        p95_time_minutes: 95th percentile (conservative bound).
        fastest_time_minutes: Fastest simulated finish.
        slowest_time_minutes: Slowest simulated finish.
        num_simulations: Number of simulations run.
        baseline_time_minutes: Predicted time without variance/environment.
        environment_factor: Multiplicative pace factor from environment.
        fitness_factor: Multiplicative pace factor from TSB.
    """

    median_time_minutes: float
    mean_time_minutes: float
    std_time_minutes: float
    p5_time_minutes: float
    p25_time_minutes: float
    p75_time_minutes: float
    p95_time_minutes: float
    fastest_time_minutes: float
    slowest_time_minutes: float
    num_simulations: int
    baseline_time_minutes: float
    environment_factor: float
    fitness_factor: float


def simulate_race(
    distance_meters: float,
    recent_race_distance_meters: float,
    recent_race_time_minutes: float,
    tsb: float = 0.0,
    environment: EnvironmentConditions | None = None,
    pace_cv: float = DEFAULT_PACE_CV,
    num_simulations: int = DEFAULT_NUM_SIMULATIONS,
    seed: int | None = None,
) -> SimulationResult:
    """Run Monte Carlo simulation of race-day performance.

    Takes an athlete's recent race result to derive VDOT, applies
    fitness/fatigue state and environmental adjustments, then runs
    stochastic simulations sampling pace from a normal distribution.

    Args:
        distance_meters: Target race distance in meters.
        recent_race_distance_meters: Distance of the reference race in meters.
        recent_race_time_minutes: Finish time of the reference race in minutes.
        tsb: Current Training Stress Balance (form). Positive = fresh,
            negative = fatigued. Default 0.0 (neutral).
        environment: Environmental conditions. None uses default (optimal).
        pace_cv: Coefficient of variation for pace sampling. Default 0.03
            (3% variation). Must be non-negative.
        num_simulations: Number of Monte Carlo iterations. Default 10,000.
        seed: Random seed for reproducibility. None for non-deterministic.

    Returns:
        SimulationResult with finish-time distribution statistics.

    Raises:
        ValueError: If distances or time are not positive, pace_cv is
            negative, or num_simulations is not positive.
    """
    _validate_simulation_inputs(
        distance_meters, recent_race_distance_meters,
        recent_race_time_minutes, pace_cv, num_simulations,
    )

    if environment is None:
        environment = EnvironmentConditions()

    rng = random.Random(seed)

    # Step 1: Derive VDOT from recent race
    vdot = compute_vdot(recent_race_distance_meters, recent_race_time_minutes)

    # Step 2: Predict baseline finish time for target distance
    baseline_time = predict_race_time(vdot, distance_meters)

    # Step 3: Compute environment pace factor (multiplicative on time)
    env_factor = _compute_environment_factor(environment, distance_meters)

    # Step 4: Compute fitness/fatigue factor from TSB
    fitness_factor = _compute_fitness_factor(tsb)

    # Step 5: Adjusted baseline = baseline * env_factor * fitness_factor
    adjusted_baseline = baseline_time * env_factor * fitness_factor

    # Step 6: Run simulations — sample from normal distribution
    simulated_times = _run_simulations(
        adjusted_baseline, pace_cv, num_simulations, rng
    )

    # Step 7: Compute statistics
    return _compute_statistics(
        simulated_times, num_simulations, baseline_time,
        env_factor, fitness_factor,
    )


def simulate_race_from_vdot(
    vdot: float,
    distance_meters: float,
    tsb: float = 0.0,
    environment: EnvironmentConditions | None = None,
    pace_cv: float = DEFAULT_PACE_CV,
    num_simulations: int = DEFAULT_NUM_SIMULATIONS,
    seed: int | None = None,
) -> SimulationResult:
    """Run Monte Carlo simulation from a known VDOT score.

    Convenience function when VDOT is already known (e.g., from stored
    athlete profile) rather than requiring a reference race.

    Args:
        vdot: Athlete's VDOT score.
        distance_meters: Target race distance in meters.
        tsb: Current Training Stress Balance. Default 0.0.
        environment: Environmental conditions. None uses default.
        pace_cv: Coefficient of variation for pace. Default 0.03.
        num_simulations: Number of iterations. Default 10,000.
        seed: Random seed for reproducibility.

    Returns:
        SimulationResult with finish-time distribution statistics.

    Raises:
        ValueError: If vdot or distance is not positive, pace_cv is
            negative, or num_simulations is not positive.
    """
    if vdot <= 0:
        raise ValueError(f"vdot must be positive, got {vdot}")
    if distance_meters <= 0:
        raise ValueError(f"distance_meters must be positive, got {distance_meters}")
    if pace_cv < 0:
        raise ValueError(f"pace_cv must be non-negative, got {pace_cv}")
    if num_simulations <= 0:
        raise ValueError(f"num_simulations must be positive, got {num_simulations}")

    if environment is None:
        environment = EnvironmentConditions()

    rng = random.Random(seed)

    baseline_time = predict_race_time(vdot, distance_meters)
    env_factor = _compute_environment_factor(environment, distance_meters)
    fitness_factor = _compute_fitness_factor(tsb)
    adjusted_baseline = baseline_time * env_factor * fitness_factor

    simulated_times = _run_simulations(
        adjusted_baseline, pace_cv, num_simulations, rng
    )

    return _compute_statistics(
        simulated_times, num_simulations, baseline_time,
        env_factor, fitness_factor,
    )


def compute_confidence_interval(
    simulated_times: list[float],
    confidence: float = 0.90,
) -> tuple[float, float]:
    """Compute a confidence interval from simulated finish times.

    Args:
        simulated_times: List of simulated finish times in minutes.
        confidence: Confidence level (e.g., 0.90 for 90%). Must be in (0, 1).

    Returns:
        Tuple of (lower_bound, upper_bound) in minutes.

    Raises:
        ValueError: If simulated_times is empty or confidence is invalid.
    """
    if not simulated_times:
        raise ValueError("simulated_times must be non-empty")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be between 0 and 1 exclusive, got {confidence}")

    sorted_times = sorted(simulated_times)
    n = len(sorted_times)
    tail = (1.0 - confidence) / 2.0
    lower_idx = max(0, int(math.floor(tail * n)))
    upper_idx = min(n - 1, int(math.ceil((1.0 - tail) * n)) - 1)

    return (sorted_times[lower_idx], sorted_times[upper_idx])


# --- Private helpers ---


def _compute_environment_factor(
    env: EnvironmentConditions,
    distance_meters: float,
) -> float:
    """Compute multiplicative pace factor from environmental conditions.

    Factor > 1.0 means slower (adverse conditions).
    Factor < 1.0 means faster (favorable conditions like tailwind).
    Factor = 1.0 means neutral.

    Args:
        env: Environmental conditions.
        distance_meters: Race distance in meters (for elevation normalization).

    Returns:
        Multiplicative factor to apply to baseline finish time.
    """
    factor = 1.0

    # Heat penalty: only applies above baseline temperature
    if env.temperature_c > HEAT_BASELINE_C:
        heat_delta = env.temperature_c - HEAT_BASELINE_C
        factor += heat_delta * HEAT_PENALTY_PER_DEGREE_C

    # Elevation gain penalty: normalized per km
    if env.elevation_gain_m > 0 and distance_meters > 0:
        distance_km = distance_meters / 1000.0
        gain_per_km = env.elevation_gain_m / distance_km
        factor += gain_per_km * ELEVATION_GAIN_PENALTY_PER_M

    # Wind: headwind slows, tailwind helps
    if env.headwind_ms != 0:
        factor += env.headwind_ms * HEADWIND_PENALTY_PER_MS

    return max(factor, 0.5)  # Floor at 0.5 to prevent nonsensical results


def _compute_fitness_factor(tsb: float) -> float:
    """Compute pace factor from Training Stress Balance.

    Positive TSB (fresh) makes the athlete faster (factor < 1.0).
    Negative TSB (fatigued) makes the athlete slower (factor > 1.0).

    Args:
        tsb: Current TSB value.

    Returns:
        Multiplicative factor for finish time.
    """
    # Negative TSB → positive adjustment → slower
    # Positive TSB → negative adjustment → faster
    adjustment = -tsb * TSB_PACE_ADJUSTMENT_PER_UNIT
    factor = 1.0 + adjustment
    return max(factor, 0.8)  # Floor: TSB can't make you more than 20% faster


def _run_simulations(
    adjusted_baseline: float,
    pace_cv: float,
    num_simulations: int,
    rng: random.Random,
) -> list[float]:
    """Run the actual Monte Carlo simulations.

    Samples finish times from a normal distribution centered on the
    adjusted baseline with standard deviation = baseline * pace_cv.

    Args:
        adjusted_baseline: Expected finish time after adjustments.
        pace_cv: Coefficient of variation for sampling.
        rng: Random number generator instance.
        num_simulations: Number of iterations.

    Returns:
        List of simulated finish times (always positive).
    """
    if pace_cv == 0.0:
        return [adjusted_baseline] * num_simulations

    std_dev = adjusted_baseline * pace_cv
    times: list[float] = []
    for _ in range(num_simulations):
        t = rng.gauss(adjusted_baseline, std_dev)
        # Floor at 50% of baseline — can't run negative time or absurdly fast
        times.append(max(t, adjusted_baseline * 0.5))

    return times


def _compute_statistics(
    simulated_times: list[float],
    num_simulations: int,
    baseline_time: float,
    env_factor: float,
    fitness_factor: float,
) -> SimulationResult:
    """Compute summary statistics from simulated finish times.

    Args:
        simulated_times: List of simulated finish times.
        num_simulations: Number of simulations run.
        baseline_time: Predicted time without variance/adjustments.
        env_factor: Environmental pace factor applied.
        fitness_factor: Fitness/fatigue pace factor applied.

    Returns:
        SimulationResult with all statistics populated.
    """
    sorted_times = sorted(simulated_times)
    n = len(sorted_times)

    mean_time = sum(sorted_times) / n
    variance = sum((t - mean_time) ** 2 for t in sorted_times) / n
    std_time = math.sqrt(variance)

    return SimulationResult(
        median_time_minutes=sorted_times[n // 2],
        mean_time_minutes=mean_time,
        std_time_minutes=std_time,
        p5_time_minutes=sorted_times[max(0, int(0.05 * n))],
        p25_time_minutes=sorted_times[max(0, int(0.25 * n))],
        p75_time_minutes=sorted_times[min(n - 1, int(0.75 * n))],
        p95_time_minutes=sorted_times[min(n - 1, int(0.95 * n))],
        fastest_time_minutes=sorted_times[0],
        slowest_time_minutes=sorted_times[-1],
        num_simulations=num_simulations,
        baseline_time_minutes=baseline_time,
        environment_factor=env_factor,
        fitness_factor=fitness_factor,
    )


def _validate_simulation_inputs(
    distance_meters: float,
    recent_race_distance_meters: float,
    recent_race_time_minutes: float,
    pace_cv: float,
    num_simulations: int,
) -> None:
    """Validate inputs for simulate_race().

    Raises:
        ValueError: On invalid inputs.
    """
    if distance_meters <= 0:
        raise ValueError(f"distance_meters must be positive, got {distance_meters}")
    if recent_race_distance_meters <= 0:
        raise ValueError(
            f"recent_race_distance_meters must be positive, got {recent_race_distance_meters}"
        )
    if recent_race_time_minutes <= 0:
        raise ValueError(
            f"recent_race_time_minutes must be positive, got {recent_race_time_minutes}"
        )
    if pace_cv < 0:
        raise ValueError(f"pace_cv must be non-negative, got {pace_cv}")
    if num_simulations <= 0:
        raise ValueError(f"num_simulations must be positive, got {num_simulations}")
