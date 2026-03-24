"""Pydantic request/response schemas for API routes.

Separate from domain models (src/models/) — these handle HTTP serialization.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class OAuthCallbackRequest(BaseModel):
    """OAuth callback request body.

    Attributes:
        code: Authorization code from OAuth provider.
    """

    code: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """JWT token pair returned after successful authentication.

    Attributes:
        access_token: Short-lived access token.
        token_type: Token type (always 'bearer').
    """

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user information.

    Attributes:
        id: User ID.
        email: User email.
        name: Display name.
        avatar_url: Profile picture URL.
    """

    id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None = None


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    """Request body for creating or updating an athlete profile.

    All fields mirror AthleteProfile. Required fields must always be
    provided; optional fields can be omitted.

    Attributes:
        name: Athlete display name.
        age: Age in years (10-100).
        vo2max: VO2max in ml/kg/min (optional, 15-90).
        vdot: VDOT score (optional, 15-85).
        weekly_mileage_base: Current weekly mileage in km.
        hr_max: Max heart rate (optional, 100-230).
        hr_rest: Resting heart rate (optional, 30-100).
        injury_history: Free-text injury history.
        risk_tolerance: Risk tolerance level.
        max_weekly_increase_pct: Max weekly load increase (0.01-0.20).
        goal_distance: Target race distance.
        goal_time_minutes: Target finish time in minutes (optional).
        training_days_per_week: Available training days (3-7).
        long_run_cap_pct: Max long run fraction (0.15-0.50).
    """

    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=10, le=100)
    vo2max: float | None = Field(default=None, ge=15.0, le=90.0)
    vdot: float | None = Field(default=None, ge=15.0, le=85.0)
    weekly_mileage_base: float = Field(ge=0.0)
    hr_max: int | None = Field(default=None, ge=100, le=230)
    hr_rest: int | None = Field(default=None, ge=30, le=100)
    injury_history: str = Field(default="", max_length=500)
    risk_tolerance: str = Field(default="moderate", pattern=r"^(conservative|moderate|aggressive)$")
    max_weekly_increase_pct: float = Field(default=0.10, ge=0.01, le=0.20)
    goal_distance: str = Field(max_length=50)
    goal_time_minutes: float | None = Field(default=None, ge=1.0)
    training_days_per_week: int = Field(default=5, ge=3, le=7)
    long_run_cap_pct: float = Field(default=0.30, ge=0.15, le=0.50)
    preferred_units: str = Field(default="metric", pattern=r"^(metric|imperial)$")


class ProfileResponse(BaseModel):
    """Athlete profile response.

    Attributes:
        id: Profile record ID.
        user_id: Owning user ID.
        name: Athlete display name.
        age: Age in years.
        vo2max: VO2max (optional).
        vdot: VDOT score (optional).
        weekly_mileage_base: Weekly mileage baseline.
        hr_max: Max heart rate (optional).
        hr_rest: Resting heart rate (optional).
        injury_history: Injury history text.
        risk_tolerance: Risk tolerance level.
        max_weekly_increase_pct: Max weekly increase fraction.
        goal_distance: Target race distance.
        goal_time_minutes: Target time (optional).
        training_days_per_week: Training days per week.
        long_run_cap_pct: Long run cap fraction.
        created_at: Profile creation time.
        updated_at: Last update time.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    age: int
    vo2max: float | None
    vdot: float | None
    weekly_mileage_base: float
    hr_max: int | None
    hr_rest: int | None
    injury_history: str
    risk_tolerance: str
    max_weekly_increase_pct: float
    goal_distance: str
    goal_time_minutes: float | None
    training_days_per_week: int
    long_run_cap_pct: float
    preferred_units: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

class PlanSummary(BaseModel):
    """Abbreviated plan info for list views.

    Attributes:
        id: Plan ID.
        approved: Whether the plan was approved.
        status: Plan lifecycle status.
        scores: Reviewer scores (optional).
        created_at: Generation time.
    """

    id: uuid.UUID
    approved: bool
    status: str
    scores: dict[str, Any] | None = None
    goal_event: str | None = None
    week_count: int | None = None
    created_at: datetime


class PlanDetail(BaseModel):
    """Full plan detail including plan data and decision log.

    Attributes:
        id: Plan ID.
        user_id: Owning user.
        athlete_snapshot: Frozen profile at generation time.
        plan_data: Full plan (weeks, workouts, phases).
        decision_log: Orchestrator decision log.
        scores: Final reviewer scores.
        approved: Whether the plan was approved.
        status: Plan lifecycle status.
        total_tokens: Tokens consumed.
        estimated_cost_usd: API cost estimate.
        created_at: Generation time.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    athlete_snapshot: dict[str, Any]
    plan_data: dict[str, Any]
    decision_log: list[dict[str, Any]]
    scores: dict[str, Any] | None = None
    approved: bool
    status: str
    total_tokens: int
    estimated_cost_usd: float
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanDebug(BaseModel):
    """Plan debug view with decision log and scores.

    Attributes:
        id: Plan ID.
        decision_log: Full orchestrator decision log.
        scores: Final reviewer scores.
        approved: Whether approved.
        total_tokens: Tokens consumed.
        estimated_cost_usd: Cost estimate.
    """

    id: uuid.UUID
    decision_log: list[dict[str, Any]]
    scores: dict[str, Any] | None = None
    approved: bool
    total_tokens: int
    estimated_cost_usd: float

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    """Simple message response for operations without complex return data.

    Attributes:
        detail: Human-readable message.
    """

    detail: str


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class PlanGenerateRequest(BaseModel):
    """Request body for triggering plan generation.

    Uses the user's saved profile by default. Optional change_type
    controls reviewer involvement.

    Attributes:
        change_type: Plan change scope (full/adaptation/tweak).
    """

    change_type: str = Field(
        default="full",
        pattern=r"^(full|adaptation|tweak)$",
        description="Plan change type: full, adaptation, or tweak",
    )


class JobResponse(BaseModel):
    """Job status response.

    Attributes:
        job_id: Job identifier.
        status: Current status.
    """

    job_id: uuid.UUID
    status: str


class JobDetailResponse(BaseModel):
    """Detailed job status with plan_id and error.

    Attributes:
        job_id: Job identifier.
        status: Current status (pending/running/complete/failed).
        plan_id: Associated plan ID (set on completion).
        error: Error message if failed.
        progress: List of progress events.
        created_at: Job creation time.
        completed_at: Job completion time.
    """

    job_id: uuid.UUID
    status: str
    plan_id: uuid.UUID | None = None
    error: str | None = None
    progress: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None
