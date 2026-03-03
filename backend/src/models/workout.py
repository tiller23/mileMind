"""Workout-related domain models."""

from enum import Enum

from pydantic import BaseModel, Field


class WorkoutType(str, Enum):
    """Types of running workouts the planner can prescribe."""

    EASY = "easy"
    LONG_RUN = "long_run"
    TEMPO = "tempo"
    INTERVAL = "interval"
    REPETITION = "repetition"
    RECOVERY = "recovery"
    MARATHON_PACE = "marathon_pace"
    FARTLEK = "fartlek"
    HILL = "hill"
    REST = "rest"
    CROSS_TRAIN = "cross_train"


class PaceZone(str, Enum):
    """Training pace zones from Daniels' Running Formula."""

    EASY = "easy"
    MARATHON = "marathon"
    THRESHOLD = "threshold"
    INTERVAL = "interval"
    REPETITION = "repetition"


class Workout(BaseModel):
    """A single prescribed workout within a training plan.

    Attributes:
        day: Day of the week (1=Monday, 7=Sunday).
        workout_type: The type of workout prescribed.
        distance_km: Planned distance in kilometers.
        pace_zone: Target pace zone for the primary effort.
        duration_minutes: Estimated total duration including warm-up/cool-down.
        intensity: Intensity factor in [0, 1]. 0=rest, 1=max effort.
        tss: Training stress score. Computed by tools, never free-generated.
        description: Human-readable workout description from the planner.
    """

    day: int = Field(ge=1, le=7, description="Day of the week (1=Monday, 7=Sunday)")
    workout_type: WorkoutType
    distance_km: float = Field(ge=0.0, description="Planned distance in kilometers")
    pace_zone: PaceZone | None = Field(
        default=None, description="Target pace zone (None for rest days)"
    )
    duration_minutes: float = Field(
        ge=0.0, description="Estimated duration in minutes"
    )
    intensity: float = Field(
        ge=0.0, le=1.0, description="Intensity factor (0=rest, 1=max)"
    )
    tss: float | None = Field(
        default=None, description="Training stress score (computed by tools)"
    )
    description: str = Field(default="", description="Workout description")


class WorkoutLog(BaseModel):
    """Actual workout data logged after completion.

    Used by the feedback adaptation loop to compare predicted vs actual
    training stress and trigger replanning when deviations exceed 15%.

    Attributes:
        workout_day: Day of the week the workout was completed.
        actual_distance_km: Actual distance covered.
        actual_duration_minutes: Actual duration in minutes.
        actual_pace_sec_per_km: Average pace in seconds per kilometer.
        avg_heart_rate: Average heart rate during the workout.
        rpe: Rate of perceived exertion (1-10 scale).
        actual_tss: Actual training stress (computed by tools from logged data).
        notes: Athlete's notes about the workout.
    """

    workout_day: int = Field(ge=1, le=7)
    actual_distance_km: float = Field(ge=0.0)
    actual_duration_minutes: float = Field(ge=0.0)
    actual_pace_sec_per_km: float | None = Field(default=None, ge=0.0)
    avg_heart_rate: int | None = Field(default=None, ge=30, le=250)
    rpe: int | None = Field(default=None, ge=1, le=10)
    actual_tss: float | None = Field(default=None)
    notes: str = Field(default="")
