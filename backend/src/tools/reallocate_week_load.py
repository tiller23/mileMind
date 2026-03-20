"""Tool wrapper: reallocate_week_load.

Wraps the deterministic ACWR validation layer to allow Claude to swap a workout
within a training week and, optionally, rebalance the remaining workouts to
preserve a target weekly TSS.  All physiological arithmetic (TSS computation,
ACWR checks) is performed exclusively by the deterministic engine.

Inputs are validated against a Pydantic model before any computation occurs.
Outputs are fully typed and returned as plain dicts for JSON serialisation by
the ToolRegistry.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.deterministic.acwr import validate_weekly_increase
from src.deterministic.training_stress import (
    DEFAULT_WORKOUT_INTENSITY,
    compute_tss,
    scale_intensity_for_target_tss,
)
from src.models.workout import WorkoutType
from src.tools.registry import ToolDefinition, ToolRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_RISK_TOLERANCES: frozenset[str] = frozenset({"conservative", "moderate", "aggressive"})

_TOOL_NAME = "reallocate_week_load"

_TOOL_DESCRIPTION = (
    "Reallocate training load within a week by swapping a workout and optionally "
    "rebalancing to maintain target load. Use this when an athlete requests a "
    "schedule change (e.g., 'swap my track workout for an easy run'). Validates "
    "the adjusted week against progression constraints."
)

# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class WorkoutEntry(BaseModel):
    """A single workout entry in the weekly plan supplied to the tool.

    Attributes:
        day: Day of the week (1=Monday, 7=Sunday).
        workout_type: A WorkoutType enum value (e.g. "easy", "tempo"). Pydantic
            validates the value against the enum automatically.
        distance_km: Planned distance in kilometres.
        duration_minutes: Planned duration in minutes.
        intensity: Intensity factor in [0, 1].  0=rest, 1=max effort.
        description: Optional human-readable description.
    """

    day: int = Field(ge=1, le=7, description="Day of the week (1=Monday, 7=Sunday)")
    workout_type: WorkoutType = Field(description="WorkoutType value (e.g. 'easy', 'tempo')")
    distance_km: float = Field(ge=0.0, description="Distance in kilometres")
    duration_minutes: float = Field(ge=0.0, description="Duration in minutes")
    intensity: float = Field(ge=0.0, le=1.0, description="Intensity factor [0, 1]")
    description: str = Field(default="", description="Optional workout description")


class ReallocateWeekInput(BaseModel):
    """Input model for the reallocate_week_load tool.

    Attributes:
        workouts: The current week's workouts.  Each entry must cover the
            mandatory workout fields; duplicate days are allowed (e.g., two
            easy runs on the same day) but the swap targets the first match.
        swap_day: The day number (1-7) whose workout should be replaced.
            If multiple workouts exist on that day, the first one is replaced.
        new_workout_type: The WorkoutType string for the replacement workout.
        new_intensity: Optional intensity override [0, 1] for the swapped
            workout.  When None, the tool infers intensity from the
            new_workout_type using canonical defaults.
        target_weekly_load: Optional target total TSS for the week.  When
            provided, the tool scales non-swapped, non-rest workouts so that
            their combined load, plus the swapped workout's load, hits the
            target.
        previous_week_load: Optional previous week's total TSS.  When
            provided, validate_weekly_increase() is called and any violation
            is recorded in the output.
        risk_tolerance: One of "conservative", "moderate", or "aggressive".
            Passed through to progression-constraint validation messaging.
    """

    workouts: list[WorkoutEntry] = Field(
        min_length=1,
        max_length=21,
        description="Current week's workouts (1-21 entries; max 3 per day)",
    )
    swap_day: int = Field(ge=1, le=7, description="Day to modify (1=Monday, 7=Sunday)")
    new_workout_type: WorkoutType = Field(description="WorkoutType value for the replacement workout")
    new_intensity: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Intensity override for the swapped workout (0-1)",
    )
    target_weekly_load: float | None = Field(
        default=None,
        ge=0.0,
        description="Target total weekly TSS to maintain after the swap",
    )
    previous_week_load: float | None = Field(
        default=None,
        ge=0.0,
        description="Previous week's total TSS for progression validation",
    )
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = Field(
        default="moderate",
        description="Risk tolerance for progression constraint validation",
    )

    @model_validator(mode="after")
    def validate_swap_day_exists(self) -> "ReallocateWeekInput":
        """Ensure swap_day corresponds to at least one workout in the list.

        Returns:
            self (unchanged) if valid.

        Raises:
            ValueError: If no workout exists on swap_day.
        """
        days = {w.day for w in self.workouts}
        if self.swap_day not in days:
            raise ValueError(
                f"swap_day {self.swap_day} has no matching workout in the supplied list. "
                f"Days present: {sorted(days)}"
            )
        return self


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class ReallocateWeekOutput(BaseModel):
    """Output model for the reallocate_week_load tool.

    Attributes:
        adjusted_workouts: Full week with the swap applied and any scaling
            applied to non-swapped workouts.
        original_load: Total TSS before reallocation.
        adjusted_load: Total TSS after reallocation.
        load_change_pct: Percentage change in weekly load
            ((adjusted - original) / original * 100), or 0 when original is 0.
        swap_summary: Human-readable description of what changed.
        validation_passed: True if no progression violations were found.
        validation_violations: List of human-readable violation strings.
    """

    adjusted_workouts: list[dict[str, Any]]
    original_load: float
    adjusted_load: float
    load_change_pct: float
    swap_summary: str
    validation_passed: bool
    validation_violations: list[str]


# Alias for the deterministic layer's canonical intensity defaults.
_DEFAULT_INTENSITY: dict[str, float] = DEFAULT_WORKOUT_INTENSITY


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_tss(duration_minutes: float, intensity: float) -> float:
    """Delegate to deterministic engine's compute_tss.

    Args:
        duration_minutes: Workout duration in minutes.
        intensity: Intensity factor in [0, 1].

    Returns:
        TSS value (non-negative float).
    """
    return compute_tss(duration_minutes, intensity)


def _resolve_intensity(workout_type: str, override: float | None) -> float:
    """Return the effective intensity for a workout type.

    Args:
        workout_type: A valid WorkoutType string value.
        override: Caller-supplied intensity override, or None.

    Returns:
        The override value if provided, otherwise the canonical default.
    """
    if override is not None:
        return override
    return _DEFAULT_INTENSITY.get(workout_type, 0.60)


def _scale_workouts_to_target(
    workouts: list[dict[str, Any]],
    swap_idx: int,
    target_load: float,
    swapped_tss: float,
) -> list[dict[str, Any]]:
    """Scale non-swapped, non-rest workouts so the week total meets target_load.

    The remaining-load budget is: target_load - swapped_tss.  That budget is
    distributed across eligible workouts (all except the swapped one and rest
    days) proportionally to their current TSS.  Intensity is back-calculated
    from the new TSS so that the duration stays unchanged.

    If there are no eligible workouts to scale, the workouts are returned
    unmodified (the total will simply differ from the target).

    Args:
        workouts: Mutable list of workout dicts (already has swapped entry).
        swap_idx: Index in `workouts` of the already-swapped entry (excluded
            from scaling).
        target_load: Target total weekly TSS.
        swapped_tss: TSS of the swapped workout (already baked into workouts).

    Returns:
        The workouts list with intensities adjusted on eligible entries.
    """
    remaining_target = target_load - swapped_tss
    if remaining_target < 0.0:
        remaining_target = 0.0

    # Identify eligible workouts (not the swapped entry, not rest days)
    eligible_indices = [
        i for i, w in enumerate(workouts)
        if i != swap_idx and w["workout_type"] != WorkoutType.REST.value
    ]

    if not eligible_indices:
        return workouts

    current_remaining = sum(
        _compute_tss(workouts[i]["duration_minutes"], workouts[i]["intensity"])
        for i in eligible_indices
    )

    if current_remaining == 0.0:
        return workouts

    scale_factor = remaining_target / current_remaining

    for i in eligible_indices:
        w = workouts[i]
        new_intensity = scale_intensity_for_target_tss(w["intensity"], scale_factor)
        new_tss = _compute_tss(w["duration_minutes"], new_intensity)
        workouts[i] = {**w, "intensity": round(new_intensity, 6), "tss": round(new_tss, 4)}

    return workouts


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def reallocate_week_load_handler(input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute the reallocate_week_load tool.

    The registry validates input_data against ReallocateWeekInput before calling
    this handler, passing the result of ``model_dump()``.  The handler therefore
    works with plain dicts and does not re-validate the input.

    Steps:
        1. Compute original TSS for each workout from the validated input dict.
        2. Apply the swap on swap_day (first matching workout).
        3. If target_weekly_load is given, scale remaining workouts.
        4. If previous_week_load is given, run validate_weekly_increase().
        5. Build and return ReallocateWeekOutput as a plain dict.

    Args:
        input_data: Validated dict produced by ``ReallocateWeekInput.model_dump()``.
            All fields have already been validated by the ToolRegistry.

    Returns:
        Dict matching ReallocateWeekOutput.

    Raises:
        ValueError: If an internal invariant is violated (should not normally
            occur after input validation).
    """
    workouts_raw: list[dict[str, Any]] = input_data["workouts"]
    swap_day: int = input_data["swap_day"]
    new_workout_type: str = (
        input_data["new_workout_type"].value
        if isinstance(input_data["new_workout_type"], WorkoutType)
        else input_data["new_workout_type"]
    )
    new_intensity_override: float | None = input_data.get("new_intensity")
    target_weekly_load: float | None = input_data.get("target_weekly_load")
    previous_week_load: float | None = input_data.get("previous_week_load")
    risk_tolerance: str = input_data.get("risk_tolerance", "moderate")

    # --- Step 1: Build mutable workout list with original TSS ---
    workouts_out: list[dict[str, Any]] = []
    for w in workouts_raw:
        wt = w["workout_type"]
        wt_str = wt.value if isinstance(wt, WorkoutType) else wt
        tss = _compute_tss(w["duration_minutes"], w["intensity"])
        workouts_out.append({
            "day": w["day"],
            "workout_type": wt_str,
            "distance_km": w["distance_km"],
            "duration_minutes": w["duration_minutes"],
            "intensity": w["intensity"],
            "description": w.get("description", ""),
            "tss": round(tss, 4),
        })

    original_load = sum(w["tss"] for w in workouts_out)

    # --- Step 2: Locate the first workout on swap_day ---
    swap_idx: int | None = None
    for i, w in enumerate(workouts_out):
        if w["day"] == swap_day:
            swap_idx = i
            break

    # The model_validator on ReallocateWeekInput guarantees swap_day exists in
    # the workouts list, so swap_idx is always set after registry validation.
    if swap_idx is None:
        raise ValueError("swap_day validated but no matching workout found")

    old_workout = workouts_out[swap_idx]
    new_intensity = _resolve_intensity(new_workout_type, new_intensity_override)
    new_tss = _compute_tss(old_workout["duration_minutes"], new_intensity)

    workouts_out[swap_idx] = {
        "day": swap_day,
        "workout_type": new_workout_type,
        "distance_km": old_workout["distance_km"],
        "duration_minutes": old_workout["duration_minutes"],
        "intensity": round(new_intensity, 6),
        "description": old_workout["description"],
        "tss": round(new_tss, 4),
    }

    swap_summary = (
        f"Day {swap_day}: replaced '{old_workout['workout_type']}' "
        f"(intensity {old_workout['intensity']:.2f}, "
        f"TSS {old_workout['tss']:.1f}) "
        f"with '{new_workout_type}' "
        f"(intensity {new_intensity:.2f}, TSS {new_tss:.1f})"
    )

    # --- Step 3: Optional load rebalancing ---
    if target_weekly_load is not None:
        workouts_out = _scale_workouts_to_target(
            workouts_out,
            swap_idx,
            target_weekly_load,
            new_tss,
        )
        swap_summary += (
            f"; remaining workouts scaled to target weekly load "
            f"{target_weekly_load:.1f} TSS"
        )

    adjusted_load = sum(w["tss"] for w in workouts_out)

    if original_load > 0.0:
        load_change_pct = (adjusted_load - original_load) / original_load * 100.0
    else:
        load_change_pct = 0.0

    # --- Step 4: Progression validation ---
    violations: list[str] = []
    if previous_week_load is not None:
        is_valid, increase_pct = validate_weekly_increase(
            previous_week=previous_week_load,
            proposed_week=adjusted_load,
        )
        if not is_valid:
            violations.append(
                f"Adjusted weekly load {adjusted_load:.1f} TSS is "
                f"{increase_pct:.0%} above previous week "
                f"({previous_week_load:.1f} TSS), "
                f"exceeding the 10% progression limit "
                f"[risk_tolerance={risk_tolerance}]"
            )

    validation_passed = len(violations) == 0

    output = ReallocateWeekOutput(
        adjusted_workouts=workouts_out,
        original_load=round(original_load, 4),
        adjusted_load=round(adjusted_load, 4),
        load_change_pct=round(load_change_pct, 2),
        swap_summary=swap_summary,
        validation_passed=validation_passed,
        validation_violations=violations,
    )
    return output.model_dump()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    """Register the reallocate_week_load tool with the given ToolRegistry.

    Args:
        registry: The ToolRegistry instance to register into.
    """
    registry.register(ToolDefinition(
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
        input_model=ReallocateWeekInput,
        handler=reallocate_week_load_handler,
    ))
