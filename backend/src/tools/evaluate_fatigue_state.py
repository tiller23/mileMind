"""Tool wrapper: evaluate_fatigue_state.

Exposes the Banister impulse-response model to the Claude tool-use API.
All physiological computation is delegated to src.deterministic.banister;
this module is exclusively responsible for input validation, dispatch, and
output classification.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from src.deterministic import banister
from src.deterministic.banister import RecoveryStatus, classify_recovery_status
from src.tools.registry import ToolDefinition, ToolRegistry

# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

_DAILY_LOADS_DESCRIPTION = (
    "Ordered list of daily training stress scores (e.g., TSS). "
    "Index 0 is the oldest day; the last element is the most recent day. "
    "Each value must be >= 0."
)


class EvaluateFatigueStateInput(BaseModel):
    """Validated input for the evaluate_fatigue_state tool.

    Attributes:
        daily_loads: Chronologically ordered daily TSS values. The list must
            contain at least one entry. All values must be non-negative.
        fitness_tau: Exponential time constant (days) for the CTL (chronic
            training load / fitness) curve. Must be a positive integer.
            Default is 42, the standard Banister literature value.
        fatigue_tau: Exponential time constant (days) for the ATL (acute
            training load / fatigue) curve. Must be a positive integer and
            strictly less than fitness_tau so that ATL reacts faster than CTL.
            Default is 7, the standard Banister literature value.
        include_series: When True the response includes full day-by-day CTL,
            ATL, and TSB arrays suitable for charting. Defaults to False to
            keep responses compact.
    """

    daily_loads: Annotated[
        list[float],
        Field(min_length=1, max_length=3650, description=_DAILY_LOADS_DESCRIPTION),
    ]
    fitness_tau: int = Field(
        default=42,
        gt=0,
        description="Time constant for CTL (fitness) decay in days. Default 42.",
    )
    fatigue_tau: int = Field(
        default=7,
        gt=0,
        description="Time constant for ATL (fatigue) decay in days. Default 7.",
    )
    include_series: bool = Field(
        default=False,
        description="Return full CTL/ATL/TSB time series for charting. Default False.",
    )

    @field_validator("daily_loads")
    @classmethod
    def loads_must_be_non_negative(cls, loads: list[float]) -> list[float]:
        """Reject negative TSS values — training stress cannot be negative.

        Args:
            loads: The raw daily_loads list from the caller.

        Returns:
            The unchanged list if all values are >= 0.

        Raises:
            ValueError: If any element is negative.
        """
        for i, val in enumerate(loads):
            if val < 0:
                raise ValueError(f"daily_loads[{i}] = {val} is negative; TSS values must be >= 0")
        return loads

    @field_validator("fatigue_tau")
    @classmethod
    def fatigue_tau_must_be_less_than_fitness_tau(cls, fatigue_tau: int) -> int:
        """Validate fatigue_tau at the field level (cross-field check done separately).

        The real cross-field constraint is enforced in the handler so that a
        meaningful error message can reference both values. This validator
        simply ensures fatigue_tau is positive (already enforced by gt=0 in
        Field, but kept here for clarity in test introspection).

        Args:
            fatigue_tau: The proposed fatigue time constant.

        Returns:
            The unchanged value.
        """
        return fatigue_tau


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class EvaluateFatigueStateOutput(BaseModel):
    """Validated output of the evaluate_fatigue_state tool.

    Attributes:
        ctl: Chronic Training Load — the long-term fitness signal. Higher CTL
            means more fitness has been accumulated.
        atl: Acute Training Load — the short-term fatigue signal. High ATL
            relative to CTL indicates accumulated tiredness.
        tsb: Training Stress Balance (CTL - ATL). Positive means the athlete
            is fresh; negative means they are fatigued.
        recovery_status: Categorical label derived from TSB via the
            deterministic engine's classify_recovery_status().
        ctl_series: Day-by-day CTL values (oldest first). Only present when
            include_series was True.
        atl_series: Day-by-day ATL values (oldest first). Only present when
            include_series was True.
        tsb_series: Day-by-day TSB values (oldest first). Only present when
            include_series was True.
    """

    ctl: float
    atl: float
    tsb: float
    recovery_status: RecoveryStatus
    ctl_series: list[float] | None = None
    atl_series: list[float] | None = None
    tsb_series: list[float] | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "Evaluate an athlete's current fatigue state by computing Chronic Training "
    "Load (CTL/fitness), Acute Training Load (ATL/fatigue), and Training Stress "
    "Balance (TSB/form) from their daily training history. Optionally returns full "
    "time series for charting."
)


def evaluate_fatigue_state_handler(input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute the evaluate_fatigue_state tool.

    Validates cross-field constraints, calls the Banister deterministic model,
    classifies recovery status, and returns a dict matching
    EvaluateFatigueStateOutput.

    Args:
        input_data: Dict produced by ``EvaluateFatigueStateInput.model_dump()``.
            Expected keys: daily_loads, fitness_tau, fatigue_tau, include_series.

    Returns:
        Dict with keys: ctl, atl, tsb, recovery_status, and optionally
        ctl_series, atl_series, tsb_series (all None when include_series=False).

    Raises:
        ValueError: If fatigue_tau >= fitness_tau (cross-field constraint), or
            if the underlying banister functions raise ValueError (e.g., empty
            daily_loads — guarded by Pydantic min_length=1 but re-raised here
            for defensive completeness).
    """
    daily_loads: list[float] = input_data["daily_loads"]
    fitness_tau: int = input_data["fitness_tau"]
    fatigue_tau: int = input_data["fatigue_tau"]
    include_series: bool = input_data["include_series"]

    # Cross-field constraint: ATL must react faster (smaller tau) than CTL.
    if fatigue_tau >= fitness_tau:
        raise ValueError(
            f"fatigue_tau ({fatigue_tau}) must be strictly less than "
            f"fitness_tau ({fitness_tau}) so that ATL reacts faster than CTL"
        )

    # Compute scalar endpoints.
    ctl = banister.compute_ctl(daily_loads, tau=fitness_tau)
    atl = banister.compute_atl(daily_loads, tau=fatigue_tau)
    tsb = banister.compute_tsb(daily_loads, fitness_tau=fitness_tau, fatigue_tau=fatigue_tau)

    recovery_status = classify_recovery_status(tsb)

    # Optionally compute full time series for charting.
    ctl_series: list[float] | None = None
    atl_series: list[float] | None = None
    tsb_series: list[float] | None = None

    if include_series:
        series = banister.compute_tsb_series(
            daily_loads,
            fitness_tau=fitness_tau,
            fatigue_tau=fatigue_tau,
        )
        ctl_series = series["ctl"]
        atl_series = series["atl"]
        tsb_series = series["tsb"]

    output = EvaluateFatigueStateOutput(
        ctl=ctl,
        atl=atl,
        tsb=tsb,
        recovery_status=recovery_status,
        ctl_series=ctl_series,
        atl_series=atl_series,
        tsb_series=tsb_series,
    )
    return output.model_dump()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    """Register the evaluate_fatigue_state tool in the given ToolRegistry.

    Args:
        registry: The ToolRegistry instance used by the agent loop.
    """
    registry.register(
        ToolDefinition(
            name="evaluate_fatigue_state",
            description=_DESCRIPTION,
            input_model=EvaluateFatigueStateInput,
            handler=evaluate_fatigue_state_handler,
        )
    )
