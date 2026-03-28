"""Pydantic request/response schemas for API routes.

Separate from domain models (src/models/) — these handle HTTP serialization.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class OAuthCallbackRequest(BaseModel):
    """OAuth callback request body.

    Attributes:
        code: Authorization code from OAuth provider.
        state: CSRF state token for verification.
    """

    code: str = Field(min_length=1)
    state: str = Field(min_length=1)


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
        has_invite: Whether the user has redeemed an invite code.
        invite_request_status: Status of their invite request (pending/approved/denied/null).
    """

    id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None = None
    role: str = "user"
    has_invite: bool = False
    invite_request_status: str | None = None


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
    weekly_mileage_base: float = Field(ge=0.0, le=500.0)
    hr_max: int | None = Field(default=None, ge=100, le=230)
    hr_rest: int | None = Field(default=None, ge=30, le=100)
    injury_history: str = Field(default="", max_length=500)
    risk_tolerance: str = Field(default="moderate", pattern=r"^(conservative|moderate|aggressive)$")
    max_weekly_increase_pct: float = Field(default=0.10, ge=0.01, le=0.20)
    goal_distance: str = Field(
        max_length=50,
        pattern=r"^[a-zA-Z0-9_ ]+$",
        description="Race distance (alphanumeric, underscores, spaces only)",
    )
    goal_time_minutes: float | None = Field(default=None, ge=1.0)
    training_days_per_week: int = Field(default=5, ge=3, le=7)
    long_run_cap_pct: float = Field(default=0.30, ge=0.15, le=0.50)
    preferred_units: str = Field(default="metric", pattern=r"^(metric|imperial)$")
    plan_duration_weeks: int = Field(default=12, ge=4, le=24)


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
    plan_duration_weeks: int
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
    estimated_cost_usd: float | None = None
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
    plan_start_date: date | None = Field(
        default=None,
        description="Plan start date (YYYY-MM-DD). Defaults to next Monday if omitted.",
    )


class PlanUpdateStartDate(BaseModel):
    """Request body for updating a plan's start date.

    Attributes:
        plan_start_date: New plan start date (YYYY-MM-DD).
    """

    plan_start_date: date = Field(description="New plan start date (YYYY-MM-DD)")


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


# ---------------------------------------------------------------------------
# Strava
# ---------------------------------------------------------------------------

class StravaConnectResponse(BaseModel):
    """Strava OAuth connect response.

    Attributes:
        auth_url: Strava authorization URL to redirect to.
        state: Raw CSRF state nonce.
        state_token: JWT-signed state token.
    """

    auth_url: str
    state: str
    state_token: str


class StravaCallbackResponse(BaseModel):
    """Strava OAuth callback response.

    Attributes:
        connected: Always True on success.
        athlete_id: Strava athlete ID.
    """

    connected: bool
    athlete_id: int


class StravaCallbackRequest(BaseModel):
    """Strava OAuth callback request body.

    Attributes:
        code: Authorization code from Strava.
        state: JWT-signed CSRF state token.
    """

    code: str = Field(min_length=1)
    state: str = Field(min_length=1)


class StravaStatusResponse(BaseModel):
    """Strava connection status.

    Attributes:
        connected: Whether Strava is connected.
        athlete_id: Strava athlete ID (if connected).
        last_sync: Last activity sync timestamp (if any).
    """

    connected: bool
    athlete_id: int | None = None
    last_sync: datetime | None = None


class StravaSyncResponse(BaseModel):
    """Result of a Strava activity sync.

    Attributes:
        imported_count: Number of newly imported activities.
        total_activities: Total activities fetched from Strava.
        suggested_weekly_mileage_km: Estimated avg weekly km (if enough data).
    """

    imported_count: int
    total_activities: int
    suggested_weekly_mileage_km: float | None = None


class WorkoutLogResponse(BaseModel):
    """A completed workout log entry.

    Attributes:
        id: Log entry ID.
        user_id: Owning user.
        plan_id: Associated plan (optional).
        source: How logged ('manual' or 'strava').
        strava_activity_id: Strava activity ID (if from Strava).
        actual_distance_km: Distance in km.
        actual_duration_minutes: Duration in minutes.
        avg_heart_rate: Average HR (optional).
        rpe: Rate of perceived exertion (optional).
        notes: Notes or activity name.
        completed_at: When the workout was done.
        created_at: Record creation time.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID | None = None
    source: str
    strava_activity_id: int | None = None
    actual_distance_km: float
    actual_duration_minutes: float
    avg_heart_rate: int | None = None
    rpe: int | None = None
    notes: str
    completed_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Invite Requests
# ---------------------------------------------------------------------------

class InviteRequestResponse(BaseModel):
    """Invite request status response.

    Attributes:
        id: Request ID.
        status: Current status (pending/approved/denied).
        created_at: When the request was submitted.
        updated_at: Last status change.
    """

    id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InviteRequestAdminResponse(BaseModel):
    """Invite request with user info for admin views.

    Attributes:
        id: Request ID.
        user_id: Requesting user's ID.
        user_email: Requesting user's email.
        user_name: Requesting user's name.
        status: Current status.
        created_at: When the request was submitted.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_name: str
    status: str
    created_at: datetime
