"""Tool wrapper: validate_progression_constraints.

Wraps ``acwr.check_safety`` and ``acwr.validate_weekly_increase`` as a single
Claude-callable tool that evaluates a proposed training week against safety
and progression constraints before the plan is finalised.

The LLM never generates ACWR, zone, or increase-percentage values directly —
all numbers are computed by the deterministic ``acwr`` module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.deterministic import acwr
from src.tools.registry import ToolDefinition, ToolRegistry

# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class ValidateProgressionInput(BaseModel):
    """Input for the validate_progression_constraints tool.

    Attributes:
        weekly_loads: Ordered list of weekly total training loads (arbitrary
            units — TSS, TRIMP, or kilometres).  Index 0 is the oldest week;
            the last entry is the *proposed* upcoming week being evaluated.
            Must contain at least 4 values so the 28-day chronic ACWR window
            is fully populated.
        risk_tolerance: Athlete risk profile.  One of ``"conservative"``,
            ``"moderate"`` (default), or ``"aggressive"``.  Controls the ACWR
            ceiling below the hard cap of 1.5 that is always enforced.
        max_weekly_increase_pct: Maximum permitted week-over-week load increase
            expressed as a decimal fraction (0.10 = 10 %).  Must be in the
            range (0.0, 0.20].  Defaults to 0.10 (the classic "10 % rule").
    """

    weekly_loads: list[float] = Field(
        min_length=4,
        max_length=520,
        description=(
            "Ordered weekly total training loads; index 0 is the oldest week, "
            "last entry is the proposed week being validated. Min 4, max 520 entries."
        ),
    )
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = Field(
        default="moderate",
        description=(
            'Athlete risk profile: "conservative", "moderate", or "aggressive". '
            "Controls the ACWR ceiling below the absolute hard cap of 1.5."
        ),
    )
    max_weekly_increase_pct: float = Field(
        default=0.10,
        gt=0.0,
        le=0.20,
        description=(
            "Maximum allowed week-over-week load increase as a decimal fraction "
            "(0.10 = 10 %). Hard-capped by the engine at 0.20 regardless of input."
        ),
    )

    @field_validator("weekly_loads")
    @classmethod
    def loads_must_be_non_negative(cls, v: list[float]) -> list[float]:
        """Ensure every load value is non-negative.

        Args:
            v: The list of weekly loads to validate.

        Returns:
            The validated list unchanged.

        Raises:
            ValueError: If any element is negative.
        """
        for i, load in enumerate(v):
            if load < 0:
                raise ValueError(
                    f"weekly_loads[{i}] must be non-negative, got {load}"
                )
        return v


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class ValidateProgressionOutput(BaseModel):
    """Output from the validate_progression_constraints tool.

    Attributes:
        passed: ``True`` when no violations were found and the proposed week
            is safe to proceed with.
        acwr: Rolling ACWR (acute 7-day / chronic 28-day) computed from the
            supplied weekly loads.
        acwr_ewma: EWMA-variant ACWR.  ``None`` if insufficient data.
        zone: Risk zone derived from the rolling ACWR.  One of ``"low"``,
            ``"safe"``, ``"warning"``, or ``"danger"``.
        violations: Human-readable descriptions of each constraint that was
            breached.  Empty list when ``passed`` is ``True``.
        weekly_increase_pct: Actual week-over-week load change for the proposed
            week relative to the previous week, expressed as a decimal fraction
            (positive = increase, negative = decrease).  ``None`` when the
            previous week's load is zero (no meaningful percentage to compute).
    """

    passed: bool = Field(description="True if no violations were found")
    acwr: float = Field(description="Rolling ACWR (acute 7-day / chronic 28-day)")
    acwr_ewma: float | None = Field(
        description="EWMA-variant ACWR; None if insufficient data"
    )
    zone: Literal["low", "safe", "warning", "danger"] = Field(
        description='Risk zone: "low", "safe", "warning", or "danger"'
    )
    violations: list[str] = Field(
        description="Violation descriptions; empty when passed=True"
    )
    weekly_increase_pct: float | None = Field(
        description=(
            "Actual week-over-week load change for the proposed week as a "
            "decimal fraction. None when the previous week load is zero."
        )
    )


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

_TOOL_NAME = "validate_progression_constraints"


def validate_progression_constraints_handler(input_data: dict) -> dict:
    """Execute the validate_progression_constraints tool.

    Calls ``acwr.check_safety`` for the full-series safety evaluation and
    ``acwr.validate_weekly_increase`` specifically for the proposed (last)
    week versus the previous week.

    Args:
        input_data: Validated input dict produced by ``ValidateProgressionInput
            .model_dump()``.  Keys: ``weekly_loads``, ``risk_tolerance``,
            ``max_weekly_increase_pct``.

    Returns:
        Dict matching ``ValidateProgressionOutput`` with keys: ``passed``,
        ``acwr``, ``acwr_ewma``, ``zone``, ``violations``,
        ``weekly_increase_pct``.

    Raises:
        ValueError: If the deterministic engine rejects the inputs (e.g.
            fewer than 4 weekly loads, unknown risk tolerance).
    """
    weekly_loads: list[float] = input_data["weekly_loads"]
    risk_tolerance: str = input_data["risk_tolerance"]
    max_weekly_increase_pct: float = input_data["max_weekly_increase_pct"]

    # --- Full-series safety check ---
    safety: acwr.SafetyResult = acwr.check_safety(
        weekly_loads=weekly_loads,
        risk_tolerance=risk_tolerance,
        max_weekly_increase_pct=max_weekly_increase_pct,
    )

    # --- Week-over-week increase for the proposed (last) week only ---
    weekly_increase_pct: float | None
    previous_week = weekly_loads[-2]
    proposed_week = weekly_loads[-1]

    _, weekly_increase_pct = acwr.validate_weekly_increase(
        previous_week=previous_week,
        proposed_week=proposed_week,
        max_increase_pct=max_weekly_increase_pct,
    )

    # When previous week load is zero, the percentage is meaningless — return None.
    if previous_week == 0.0:
        weekly_increase_pct = None

    output = ValidateProgressionOutput(
        passed=safety.safe,
        acwr=safety.acwr,
        acwr_ewma=safety.acwr_ewma,
        zone=safety.zone,
        violations=list(safety.violations),
        weekly_increase_pct=weekly_increase_pct,
    )
    return output.model_dump()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTION = (
    "Validate a proposed training week against safety and progression constraints. "
    "Checks ACWR (rolling and EWMA), weekly mileage increase limits, and spike "
    "detection. Returns pass/fail with specific violation details. Must be called "
    "before finalizing any training plan."
)


def register(registry: ToolRegistry) -> None:
    """Register the validate_progression_constraints tool with the given registry.

    Args:
        registry: The ``ToolRegistry`` instance to register the tool into.

    Raises:
        ValueError: If a tool with the same name is already registered.
    """
    registry.register(
        ToolDefinition(
            name=_TOOL_NAME,
            description=_TOOL_DESCRIPTION,
            input_model=ValidateProgressionInput,
            handler=validate_progression_constraints_handler,
        )
    )
