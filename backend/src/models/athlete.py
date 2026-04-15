"""Athlete profile domain models."""

import hashlib
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RiskTolerance(str, Enum):
    """Athlete risk tolerance levels for progression constraints.

    Maps directly to ACWR ceiling presets in the deterministic engine.
    """

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class InjuryTag(str, Enum):
    """Structured injury history tags used by the strength playbook.

    Coexists with the free-text ``injury_history`` field; these tags
    drive deterministic exercise selection and contraindication filtering.

    No "none" sentinel — represent "no injuries" as an empty tuple.
    """

    KNEE = "knee"
    IT_BAND = "it_band"
    PLANTAR_FASCIITIS = "plantar_fasciitis"
    ACHILLES = "achilles"
    HIP = "hip"
    LOWER_BACK = "lower_back"
    HAMSTRING = "hamstring"
    SHIN_SPLINTS = "shin_splints"


class AthleteProfile(BaseModel):
    """An athlete's profile used by tools and the planner agent.

    Contains the baseline data needed to compute training zones,
    evaluate fatigue state, and validate progression constraints.

    Attributes:
        name: Athlete display name.
        age: Age in years (used for HR max estimation).
        vo2max: Measured or estimated VO2max in ml/kg/min.
        vdot: VDOT score derived from recent race. Takes priority over vo2max
            for pace zone calculations.
        weekly_mileage_base: Current baseline weekly mileage in km.
        hr_max: Maximum heart rate in bpm. Estimated from age if not provided.
        hr_rest: Resting heart rate in bpm.
        injury_history: Free-text injury history for planner context.
        risk_tolerance: Controls how aggressively the system progresses load.
        max_weekly_increase_pct: Custom weekly load increase limit (0.0-0.2).
        goal_distance: Target race distance key (e.g., "5K", "marathon").
        goal_time_minutes: Target finish time in minutes (optional).
        training_days_per_week: Number of available training days (3-7).
        long_run_cap_pct: Max fraction of weekly mileage in a single run.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=100, description="Athlete display name")
    age: int = Field(ge=10, le=100, description="Age in years")
    vo2max: float | None = Field(default=None, ge=15.0, le=90.0, description="VO2max in ml/kg/min")
    vdot: float | None = Field(default=None, ge=15.0, le=85.0, description="VDOT score")
    weekly_mileage_base: float = Field(ge=0.0, description="Current weekly mileage baseline in km")
    hr_max: int | None = Field(default=None, ge=100, le=230, description="Max heart rate in bpm")
    hr_rest: int | None = Field(
        default=None, ge=30, le=100, description="Resting heart rate in bpm"
    )
    injury_history: str = Field(
        default="", max_length=500, description="Injury history for planner context"
    )
    risk_tolerance: RiskTolerance = Field(default=RiskTolerance.MODERATE)
    max_weekly_increase_pct: float = Field(
        default=0.10,
        ge=0.01,
        le=0.20,
        description="Max weekly load increase as fraction (0.10 = 10%)",
    )
    goal_distance: str = Field(
        max_length=50, description="Target race distance (e.g., '5K', 'marathon')"
    )
    goal_time_minutes: float | None = Field(
        default=None, ge=1.0, description="Target finish time in minutes"
    )
    training_days_per_week: int = Field(
        default=5, ge=3, le=7, description="Available training days per week"
    )
    long_run_cap_pct: float = Field(
        default=0.30,
        ge=0.15,
        le=0.50,
        description="Max fraction of weekly mileage in a single long run",
    )
    preferred_units: str = Field(
        default="metric",
        pattern=r"^(metric|imperial)$",
        description="Distance units preference: metric (km) or imperial (miles)",
    )
    plan_duration_weeks: int = Field(
        default=12,
        ge=4,
        le=24,
        description="Desired training plan length in weeks (4-24)",
    )
    injury_tags: tuple[InjuryTag, ...] = Field(
        default=(),
        description="Structured injury history tags for strength playbook selection",
    )
    current_acute_injury: bool = Field(
        default=False,
        description="User has flagged a current (not historical) injury; routes to PT gate",
    )
    current_injury_description: str = Field(
        default="",
        max_length=500,
        description="Optional description of current injury",
    )

    def cache_key(self, *, salt: str = "") -> str:
        """Deterministic SHA-256 hash for same-profile deduplication.

        Returns a unique key for this exact profile. Any field difference
        (even a single character in injury_history) produces a different key.
        This is NOT a similarity match — only identical profiles share a key.

        Args:
            salt: Extra context to include (e.g., model versions, change_type).

        Returns:
            64-character lowercase hex SHA-256 digest.
        """
        payload = salt + self.model_dump_json()
        return hashlib.sha256(payload.encode()).hexdigest()
