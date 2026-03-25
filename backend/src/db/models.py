"""SQLAlchemy ORM models for the MileMind database.

Maps to the PostgreSQL schema defined in the Phase 5 plan.
All tables use UUID primary keys and UTC timestamps.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.models.athlete import AthleteProfile, RiskTolerance

# Use JSONB on Postgres, plain JSON on SQLite (tests)
JSONB = PG_JSONB().with_variant(JSON, "sqlite")


def _utcnow() -> datetime:
    """Return current UTC datetime.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    """Generate a new UUID4.

    Returns:
        New UUID.
    """
    return uuid.uuid4()


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class User(Base):
    """Registered user account.

    Attributes:
        id: Unique user identifier.
        email: User email (unique).
        name: Display name.
        auth_provider: OAuth provider ('google', 'apple', or 'demo').
        auth_provider_id: Provider's unique user ID.
        avatar_url: Profile picture URL.
        role: User role ('user' or 'admin').
        invite_code_used: Invite code redeemed by this user (nullable).
        created_at: Account creation time.
        updated_at: Last profile update time.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    auth_provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    invite_code_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    profile: Mapped[DBAthleteProfile | None] = relationship(
        "DBAthleteProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    plans: Mapped[list[TrainingPlan]] = relationship(
        "TrainingPlan", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("auth_provider", "auth_provider_id", name="uq_auth_provider_id"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_user_role"),
    )


class DBAthleteProfile(Base):
    """Mutable athlete profile stored in the database.

    Mirrors AthleteProfile fields but is mutable (editable by user).
    Use ``to_athlete_profile()`` to create a frozen Pydantic snapshot
    for plan generation.

    Attributes:
        id: Profile record ID.
        user_id: Owning user (one-to-one).
        name: Athlete display name.
        age: Age in years.
        vo2max: VO2max in ml/kg/min (optional).
        vdot: VDOT score (optional).
        weekly_mileage_base: Current weekly mileage baseline in km.
        hr_max: Max heart rate (optional).
        hr_rest: Resting heart rate (optional).
        injury_history: Free-text injury history.
        risk_tolerance: Risk tolerance level.
        max_weekly_increase_pct: Max weekly load increase fraction.
        goal_distance: Target race distance.
        goal_time_minutes: Target finish time (optional).
        training_days_per_week: Available training days.
        long_run_cap_pct: Max long run fraction.
        created_at: Profile creation time.
        updated_at: Last update time.
    """

    __tablename__ = "athlete_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # AthleteProfile fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    vo2max: Mapped[float | None] = mapped_column(Float, nullable=True)
    vdot: Mapped[float | None] = mapped_column(Float, nullable=True)
    weekly_mileage_base: Mapped[float] = mapped_column(Float, nullable=False)
    hr_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_rest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injury_history: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(String(20), default="moderate", nullable=False)
    max_weekly_increase_pct: Mapped[float] = mapped_column(Float, default=0.10, nullable=False)
    goal_distance: Mapped[str] = mapped_column(String(50), nullable=False)
    goal_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_days_per_week: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    long_run_cap_pct: Mapped[float] = mapped_column(Float, default=0.30, nullable=False)
    preferred_units: Mapped[str] = mapped_column(String(10), default="metric", nullable=False)
    plan_duration_weeks: Mapped[int] = mapped_column(Integer, default=12, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="profile")

    __table_args__ = (
        CheckConstraint("age BETWEEN 10 AND 100", name="ck_age_range"),
        CheckConstraint("vo2max IS NULL OR (vo2max BETWEEN 15.0 AND 90.0)", name="ck_vo2max"),
        CheckConstraint("vdot IS NULL OR (vdot BETWEEN 15.0 AND 85.0)", name="ck_vdot"),
        CheckConstraint("weekly_mileage_base >= 0", name="ck_mileage_positive"),
        CheckConstraint(
            "hr_max IS NULL OR (hr_max BETWEEN 100 AND 230)", name="ck_hr_max_range"
        ),
        CheckConstraint(
            "hr_rest IS NULL OR (hr_rest BETWEEN 30 AND 100)", name="ck_hr_rest_range"
        ),
    )

    def to_athlete_profile(self) -> AthleteProfile:
        """Create a frozen AthleteProfile snapshot from this mutable DB record.

        Returns:
            Immutable AthleteProfile Pydantic model for plan generation.
        """
        return AthleteProfile(
            name=self.name,
            age=self.age,
            vo2max=self.vo2max,
            vdot=self.vdot,
            weekly_mileage_base=self.weekly_mileage_base,
            hr_max=self.hr_max,
            hr_rest=self.hr_rest,
            injury_history=self.injury_history,
            risk_tolerance=RiskTolerance(self.risk_tolerance),
            max_weekly_increase_pct=self.max_weekly_increase_pct,
            goal_distance=self.goal_distance,
            goal_time_minutes=self.goal_time_minutes,
            training_days_per_week=self.training_days_per_week,
            long_run_cap_pct=self.long_run_cap_pct,
            preferred_units=self.preferred_units,
            plan_duration_weeks=self.plan_duration_weeks,
        )


class TrainingPlan(Base):
    """A generated training plan with decision log and scores.

    Attributes:
        id: Plan identifier.
        user_id: Owning user.
        athlete_snapshot: Frozen AthleteProfile at generation time (JSONB).
        plan_data: Full plan data (weeks, workouts, phases) as JSONB.
        decision_log: Orchestrator decision log as JSONB array.
        scores: Final ReviewerScores as JSONB.
        approved: Whether the plan passed review.
        status: Plan lifecycle status (active/superseded/archived).
        total_tokens: Total tokens consumed during generation.
        estimated_cost_usd: Estimated API cost.
        created_at: Generation time.
        superseded_by: ID of the plan that replaced this one.
    """

    __tablename__ = "training_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    athlete_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    plan_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision_log: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_plans.id"), nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="plans")
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'superseded', 'archived')",
            name="ck_plan_status",
        ),
        Index("idx_plans_user_status", "user_id", "status"),
    )


class WorkoutLog(Base):
    """A completed workout log entry.

    Attributes:
        id: Log entry ID.
        user_id: Owning user.
        plan_id: Associated plan (optional).
        week_number: Plan week number (optional).
        day: Day of week 1-7 (optional).
        source: How the workout was logged ('manual' or 'strava').
        strava_activity_id: Strava activity ID (unique, optional).
        actual_distance_km: Actual distance in km.
        actual_duration_minutes: Actual duration in minutes.
        avg_heart_rate: Average heart rate (optional).
        rpe: Rate of perceived exertion 1-10 (optional).
        actual_tss: Computed TSS (optional).
        notes: User notes.
        completed_at: When the workout was completed.
        created_at: Record creation time.
    """

    __tablename__ = "workout_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_plans.id"), nullable=True
    )
    week_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    strava_activity_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    actual_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    actual_duration_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    avg_heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpe: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_tss: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("day IS NULL OR (day BETWEEN 1 AND 7)", name="ck_day_range"),
        CheckConstraint("rpe IS NULL OR (rpe BETWEEN 1 AND 10)", name="ck_rpe_range"),
        Index("idx_logs_user_date", "user_id", "completed_at"),
    )


class Job(Base):
    """Async job tracking for plan generation and chat responses.

    Attributes:
        id: Job identifier.
        user_id: Owning user.
        plan_id: Associated plan (set on completion).
        job_type: Type of job (plan_generation, chat_response).
        status: Job status (pending/running/complete/failed).
        progress: SSE event history as JSONB array.
        error: Error message if failed.
        created_at: Job creation time.
        completed_at: Job completion time.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_plans.id"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(30), default="plan_generation", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_jobs_user", "user_id"),
    )


class ChatMessage(Base):
    """Chat message in plan negotiation history.

    Attributes:
        id: Message identifier.
        plan_id: Associated plan.
        user_id: Owning user.
        role: Message role ('user' or 'assistant').
        content: Message content.
        change_type: Plan change classification (TWEAK/ADAPTATION/FULL).
        metadata: Token usage, cost info as JSONB.
        created_at: Message creation time.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    plan: Mapped[TrainingPlan] = relationship("TrainingPlan", back_populates="chat_messages")

    __table_args__ = (
        Index("idx_chat_plan", "plan_id", "created_at"),
    )


class StravaToken(Base):
    """Strava OAuth tokens for a user.

    Attributes:
        user_id: Owning user (primary key, one-to-one).
        strava_athlete_id: Strava's athlete ID.
        access_token: Current access token.
        refresh_token: Refresh token for renewal.
        expires_at: Token expiry time.
        scope: Granted OAuth scopes.
        created_at: Token creation time.
        updated_at: Last token refresh time.
    """

    __tablename__ = "strava_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    strava_athlete_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class RevokedToken(Base):
    """Revoked JWT tokens for logout enforcement.

    Tokens are added here on logout and checked on every authenticated request.
    Expired entries are cleaned up periodically.

    Attributes:
        jti: JWT token ID (unique identifier for the token).
        expires_at: When the original token would have expired.
        revoked_at: When the token was revoked.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class InviteCode(Base):
    """Invite codes that gate access to plan generation.

    Users can sign up and browse freely, but need a redeemed invite code
    to generate training plans.

    Attributes:
        code: The invite code string (e.g., 'MILE-A1B2').
        max_uses: Maximum number of times this code can be redeemed.
        use_count: Current number of redemptions.
        expires_at: Optional expiry time for the code.
        created_at: When the code was created.
    """

    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
