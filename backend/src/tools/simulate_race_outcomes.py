"""Tool wrapper: simulate_race_outcomes.

Exposes the Monte Carlo race simulation engine as a Claude-callable tool.
The LLM provides athlete fitness state and race parameters; all stochastic
math is performed by monte_carlo.py — the LLM never generates numeric
predictions itself.

Supports two fitness-input paths:

1. Direct VDOT: caller supplies ``vdot`` (e.g. from a stored athlete profile).
2. Reference race: caller supplies ``recent_race_distance`` and
   ``recent_race_time_minutes``; VDOT is derived internally via the
   Daniels-Gilbert equation.

Exactly one path must be specified per call.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.deterministic import daniels, monte_carlo
from src.tools.registry import ToolDefinition, ToolRegistry

# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

_VALID_DISTANCES = list(daniels.RACE_DISTANCES.keys())
_DISTANCE_HELP = "Must be one of: " + ", ".join(f'"{k}"' for k in _VALID_DISTANCES) + "."


class SimulateRaceInput(BaseModel):
    """Validated input for the simulate_race_outcomes tool.

    Attributes:
        vdot: Athlete VDOT score. Use this path when VDOT is already known
            (e.g. from a stored profile or a prior compute_training_stress
            call). Mutually exclusive with the reference-race path.
        recent_race_distance: Distance key for the reference race used to
            derive VDOT. Must be a key from daniels.RACE_DISTANCES. Required
            when ``vdot`` is not provided.
        recent_race_time_minutes: Finish time of the reference race in
            minutes (e.g. 20.5 for a 20:30 5K). Required when ``vdot``
            is not provided.
        target_distance: Race distance to simulate. Must be a key from
            daniels.RACE_DISTANCES.
        tsb: Current Training Stress Balance (form). Positive = well-rested,
            negative = fatigued. Default 0.0 (neutral).
        temperature_c: Race-day temperature in Celsius. Pace degrades above
            18 C. Default 18.0 (optimal).
        elevation_gain_m: Total course elevation gain in meters. More gain
            means slower predicted times. Default 0.0 (flat).
        headwind_ms: Average headwind in m/s. Positive = headwind (slower),
            negative = tailwind (faster). Default 0.0.
        num_simulations: Number of Monte Carlo iterations. Default 10,000.
        seed: Random seed for reproducibility. Omit for non-deterministic
            behavior.
    """

    vdot: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Athlete VDOT score (positive float). Provide this OR the "
            "recent_race_distance + recent_race_time_minutes pair — not both."
        ),
    )
    recent_race_distance: str | None = Field(
        default=None,
        description=("Distance key of the reference race used to derive VDOT. " + _DISTANCE_HELP),
    )
    recent_race_time_minutes: float | None = Field(
        default=None,
        gt=0,
        description="Finish time of the reference race in minutes (must be positive).",
    )
    target_distance: str = Field(
        description=("Race distance to simulate. " + _DISTANCE_HELP),
    )
    tsb: float = Field(
        default=0.0,
        description=(
            "Current Training Stress Balance. Positive = fresh/rested, "
            "negative = fatigued. Typical range: -30 to +25."
        ),
    )
    temperature_c: float = Field(
        default=18.0,
        description="Race-day temperature in Celsius. Optimal is 18 C.",
    )
    elevation_gain_m: float = Field(
        default=0.0,
        ge=0,
        description="Total course elevation gain in meters. Must be non-negative.",
    )
    headwind_ms: float = Field(
        default=0.0,
        description=(
            "Average headwind in m/s. Positive = headwind (slower), "
            "negative = tailwind (faster)."
        ),
    )
    num_simulations: int = Field(
        default=10_000,
        gt=0,
        le=1_000_000,
        description="Number of Monte Carlo iterations. Default 10,000. Max 1,000,000.",
    )
    seed: int | None = Field(
        default=None,
        description=(
            "Random seed for reproducibility. Omit to get non-deterministic " "results each call."
        ),
    )

    @model_validator(mode="after")
    def _validate_fitness_input(self) -> SimulateRaceInput:
        """Ensure exactly one fitness-input path is specified.

        Raises:
            ValueError: If neither path nor both paths are provided.
        """
        has_vdot = self.vdot is not None
        has_race = (
            self.recent_race_distance is not None and self.recent_race_time_minutes is not None
        )
        partial_race = (self.recent_race_distance is None) != (
            self.recent_race_time_minutes is None
        )

        if partial_race:
            raise ValueError(
                "recent_race_distance and recent_race_time_minutes must both be "
                "provided together, or both omitted."
            )
        if not has_vdot and not has_race:
            raise ValueError(
                "Must provide either 'vdot' or both 'recent_race_distance' and "
                "'recent_race_time_minutes'."
            )
        if has_vdot and has_race:
            raise ValueError("Provide either 'vdot' or the recent-race pair, not both.")
        return self

    @model_validator(mode="after")
    def _validate_distance_keys(self) -> SimulateRaceInput:
        """Ensure distance keys are valid entries in RACE_DISTANCES.

        Raises:
            ValueError: If target_distance or recent_race_distance is not
                a recognised key.
        """
        valid = set(daniels.RACE_DISTANCES.keys())
        if self.target_distance not in valid:
            raise ValueError(
                f"target_distance '{self.target_distance}' is not a recognised "
                f"distance key. Valid keys: {sorted(valid)}"
            )
        if self.recent_race_distance is not None and self.recent_race_distance not in valid:
            raise ValueError(
                f"recent_race_distance '{self.recent_race_distance}' is not a "
                f"recognised distance key. Valid keys: {sorted(valid)}"
            )
        return self


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class SimulateRaceOutput(BaseModel):
    """Structured output from the simulate_race_outcomes tool.

    All time fields are in minutes. The percentile fields bracket the
    likely finish-time range at various confidence levels.

    Attributes:
        median_time_minutes: Median (50th-percentile) predicted finish time.
        mean_time_minutes: Arithmetic mean of all simulated finish times.
        std_time_minutes: Standard deviation of simulated finish times.
        p5_time_minutes: 5th-percentile finish time (optimistic bound —
            only 5% of simulations were faster).
        p25_time_minutes: 25th-percentile finish time.
        p75_time_minutes: 75th-percentile finish time.
        p95_time_minutes: 95th-percentile finish time (conservative bound —
            95% of simulations finished faster than this).
        fastest_time_minutes: Fastest single simulated finish time.
        slowest_time_minutes: Slowest single simulated finish time.
        baseline_time_minutes: Predicted time before variance and
            environmental adjustments are applied.
        num_simulations: Number of Monte Carlo iterations that were run.
        environment_factor: Multiplicative factor applied to baseline time
            from environmental conditions (>1.0 = adverse, <1.0 = favorable).
        fitness_factor: Multiplicative factor applied to baseline time from
            TSB (>1.0 = fatigued, <1.0 = fresh).
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
    baseline_time_minutes: float
    num_simulations: int
    environment_factor: float
    fitness_factor: float


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def simulate_race_outcomes_handler(input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute the Monte Carlo race simulation and return a serialized result.

    Resolves distance keys to meters, constructs the EnvironmentConditions
    object, delegates all computation to the deterministic monte_carlo module,
    and converts the resulting SimulationResult dataclass into a plain dict
    that matches SimulateRaceOutput.

    Args:
        input_data: Validated input dict produced by
            ``SimulateRaceInput.model_dump()``. Keys mirror the
            SimulateRaceInput field names.

    Returns:
        Dict matching SimulateRaceOutput field names. All time values are
        in minutes.

    Raises:
        ValueError: If distance keys are not found in daniels.RACE_DISTANCES
            (should be caught by input validation) or if the underlying
            simulation raises due to invalid numeric inputs.
        KeyError: Should never occur for validated inputs; re-raised if a
            distance key lookup fails unexpectedly.
    """
    # Resolve target distance to meters
    target_distance_m: float = daniels.RACE_DISTANCES[input_data["target_distance"]]

    # Build environment conditions
    environment = monte_carlo.EnvironmentConditions(
        temperature_c=input_data["temperature_c"],
        elevation_gain_m=input_data["elevation_gain_m"],
        headwind_ms=input_data["headwind_ms"],
    )

    # Shared kwargs for both simulation paths
    common_kwargs: dict[str, Any] = {
        "tsb": input_data["tsb"],
        "environment": environment,
        "num_simulations": input_data["num_simulations"],
        "seed": input_data["seed"],
    }

    # Dispatch to the appropriate simulation function
    if input_data["vdot"] is not None:
        result: monte_carlo.SimulationResult = monte_carlo.simulate_race_from_vdot(
            vdot=input_data["vdot"],
            distance_meters=target_distance_m,
            **common_kwargs,
        )
    else:
        recent_distance_m: float = daniels.RACE_DISTANCES[input_data["recent_race_distance"]]
        result = monte_carlo.simulate_race(
            distance_meters=target_distance_m,
            recent_race_distance_meters=recent_distance_m,
            recent_race_time_minutes=input_data["recent_race_time_minutes"],
            **common_kwargs,
        )

    # Convert dataclass to dict (field names already match SimulateRaceOutput)
    output = SimulateRaceOutput(
        median_time_minutes=result.median_time_minutes,
        mean_time_minutes=result.mean_time_minutes,
        std_time_minutes=result.std_time_minutes,
        p5_time_minutes=result.p5_time_minutes,
        p25_time_minutes=result.p25_time_minutes,
        p75_time_minutes=result.p75_time_minutes,
        p95_time_minutes=result.p95_time_minutes,
        fastest_time_minutes=result.fastest_time_minutes,
        slowest_time_minutes=result.slowest_time_minutes,
        baseline_time_minutes=result.baseline_time_minutes,
        num_simulations=result.num_simulations,
        environment_factor=result.environment_factor,
        fitness_factor=result.fitness_factor,
    )
    return output.model_dump()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "Run a Monte Carlo simulation of race-day performance. Predicts "
    "finish-time distributions with confidence intervals based on current "
    "fitness (VDOT or recent race), fatigue state (TSB), and environmental "
    "conditions (temperature, elevation, wind)."
)


def register(registry: ToolRegistry) -> None:
    """Register the simulate_race_outcomes tool with the given ToolRegistry.

    Args:
        registry: The ToolRegistry instance to register into.
    """
    registry.register(
        ToolDefinition(
            name="simulate_race_outcomes",
            description=_DESCRIPTION,
            input_model=SimulateRaceInput,
            handler=simulate_race_outcomes_handler,
        )
    )
