"""Tool wrapper: compute_training_stress.

Wraps the Coggan/Allen TSS formula as a Claude-callable tool. The LLM supplies
workout metadata; this module delegates all arithmetic to the deterministic
engine and returns a structured result that the agent may read but must never
fabricate.

The TSS formula and load classification live in
``src.deterministic.training_stress`` — this wrapper only handles I/O
validation and intensity factor resolution (HR-based override).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from src.deterministic.training_stress import (
    DEFAULT_THRESHOLD_HR,
    LoadClassification,
    classify_load,
    compute_tss,
    hr_to_intensity_factor,
)
from src.models.workout import WorkoutType
from src.tools.registry import ToolDefinition, ToolRegistry

# ---------------------------------------------------------------------------
# Pydantic I/O models
# ---------------------------------------------------------------------------


class ComputeTrainingStressInput(BaseModel):
    """Input model for the compute_training_stress tool.

    Attributes:
        workout_type: One of the WorkoutType enum values (e.g. "easy", "tempo").
        duration_minutes: Total workout duration in minutes. Must be > 0.
        intensity: Intensity factor on [0, 1]. 0 = complete rest, 1 = maximal
            all-out effort. Maps directly to the IF used in the TSS formula
            unless avg_heart_rate is also supplied (see below).
        distance_km: Optional distance in kilometres. Stored in the audit trail
            but does not affect TSS computation.
        avg_heart_rate: Optional average heart rate in bpm. When supplied, the
            effective intensity factor is re-derived as
            avg_heart_rate / DEFAULT_THRESHOLD_HR, clamped to [0, 1]. This
            overrides the ``intensity`` field for IF calculation.
    """

    workout_type: WorkoutType = Field(description="Type of workout (e.g. 'easy', 'tempo')")
    duration_minutes: float = Field(gt=0, description="Total workout duration in minutes")
    intensity: float = Field(ge=0.0, le=1.0, description="Intensity factor [0, 1]")
    distance_km: float | None = Field(
        default=None, gt=0, description="Distance in kilometres (optional)"
    )
    avg_heart_rate: int | None = Field(
        default=None, ge=30, le=250, description="Average heart rate in bpm (optional)"
    )

    @model_validator(mode="after")
    def rest_workout_intensity_check(self) -> "ComputeTrainingStressInput":
        """Warn (via clamping) when a REST workout has non-zero intensity.

        REST workouts should have intensity 0. If the caller passes a non-zero
        value we silently clamp to 0 rather than raising, because a minor
        miscommunication from the LLM should not surface as a hard error.
        """
        if self.workout_type == WorkoutType.REST:
            object.__setattr__(self, "intensity", 0.0)
        return self


class ComputeTrainingStressOutput(BaseModel):
    """Output model for the compute_training_stress tool.

    Attributes:
        tss: Computed Training Stress Score (non-negative float).
        load_classification: Categorical label derived from TSS magnitude.
        intensity_factor: The effective IF actually used in the calculation.
            Equals the ``intensity`` input, or HR-derived IF when avg_heart_rate
            was supplied.
        duration_hours: Workout duration converted to hours for reference.
    """

    tss: float = Field(ge=0.0, description="Training Stress Score")
    load_classification: LoadClassification = Field(
        description="Load category: easy / moderate / hard / very_hard"
    )
    intensity_factor: float = Field(
        ge=0.0, le=1.0, description="Effective intensity factor used in computation"
    )
    duration_hours: float = Field(gt=0, description="Duration in hours (for reference)")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_intensity_factor(intensity: float, avg_heart_rate: int | None) -> float:
    """Return the intensity factor to use in the TSS formula.

    When avg_heart_rate is provided, delegates to the deterministic engine's
    hr_to_intensity_factor(). Otherwise uses the caller-supplied intensity
    directly.

    Args:
        intensity: Raw intensity input from the caller, in [0, 1].
        avg_heart_rate: Optional average heart rate in bpm.

    Returns:
        Effective intensity factor in [0, 1].
    """
    if avg_heart_rate is not None:
        return hr_to_intensity_factor(avg_heart_rate, DEFAULT_THRESHOLD_HR)
    return intensity


def _classify_load(tss: float) -> LoadClassification:
    """Delegate to deterministic engine's classify_load.

    Args:
        tss: Non-negative training stress score.

    Returns:
        One of "easy", "moderate", "hard", or "very_hard".
    """
    return classify_load(tss)


def _compute_tss(duration_minutes: float, intensity_factor: float) -> float:
    """Delegate to deterministic engine's compute_tss.

    Args:
        duration_minutes: Workout duration in minutes (> 0).
        intensity_factor: Effective intensity factor in [0, 1].

    Returns:
        TSS value (non-negative float).
    """
    return compute_tss(duration_minutes, intensity_factor)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def compute_training_stress_handler(input_data: dict) -> dict:
    """Execute the TSS computation and return a serialisable output dict.

    This function is the handler registered with the ToolRegistry. It receives
    a pre-validated dict (produced by ``ComputeTrainingStressInput.model_dump``),
    performs all deterministic arithmetic, and returns a dict that conforms to
    ``ComputeTrainingStressOutput``.

    Args:
        input_data: Validated input dict with keys matching
            ``ComputeTrainingStressInput`` fields.

    Returns:
        Dict with keys matching ``ComputeTrainingStressOutput`` fields:
        ``tss``, ``load_classification``, ``intensity_factor``,
        ``duration_hours``.

    Raises:
        ValueError: If duration_minutes is not positive (guard for edge cases
            that slip past Pydantic, e.g. floating-point underflow).
    """
    duration_minutes: float = input_data["duration_minutes"]
    intensity: float = input_data["intensity"]
    avg_heart_rate: int | None = input_data.get("avg_heart_rate")

    if duration_minutes <= 0:
        raise ValueError(f"duration_minutes must be positive, got {duration_minutes}")

    # REST workouts always have zero stress regardless of caller-supplied intensity.
    # The Pydantic model_validator handles this when inputs flow through the registry,
    # but callers that invoke the handler directly (e.g. tests) get the same guarantee.
    try:
        if WorkoutType(input_data.get("workout_type", "")) == WorkoutType.REST:
            intensity = 0.0
    except ValueError:
        pass  # Unknown workout_type will fail schema validation upstream; ignore here.

    intensity_factor = _resolve_intensity_factor(intensity, avg_heart_rate)
    tss = _compute_tss(duration_minutes, intensity_factor)
    classification = _classify_load(tss)
    duration_hours = duration_minutes / 60.0

    output = ComputeTrainingStressOutput(
        tss=tss,
        load_classification=classification,
        intensity_factor=intensity_factor,
        duration_hours=duration_hours,
    )
    return output.model_dump()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    """Register the compute_training_stress tool with the given registry.

    Args:
        registry: The shared ToolRegistry instance used by the agent loop.
    """
    tool = ToolDefinition(
        name="compute_training_stress",
        description=(
            "Compute the Training Stress Score (TSS) for a single workout based on its "
            "type, duration, and intensity. Returns TSS value and load classification. "
            "Use this to quantify the physiological cost of any workout."
        ),
        input_model=ComputeTrainingStressInput,
        handler=compute_training_stress_handler,
    )
    registry.register(tool)
