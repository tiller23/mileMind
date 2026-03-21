"""Tests for SQLAlchemy ORM models and the to_athlete_profile() snapshot."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Base,
    ChatMessage,
    DBAthleteProfile,
    Job,
    StravaToken,
    TrainingPlan,
    User,
    WorkoutLog,
)
from src.models.athlete import AthleteProfile, RiskTolerance


class TestUserModel:
    """Tests for the User ORM model."""

    async def test_create_user(self, db_session: AsyncSession) -> None:
        """User can be created with required fields."""
        user = User(
            email="alice@example.com",
            name="Alice",
            auth_provider="google",
            auth_provider_id="g-alice-123",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.email == "alice@example.com"
        assert user.name == "Alice"
        assert user.created_at is not None

    async def test_user_email_unique(self, db_session: AsyncSession) -> None:
        """Duplicate emails raise IntegrityError."""
        user1 = User(
            email="dup@example.com",
            name="User 1",
            auth_provider="google",
            auth_provider_id="g-1",
        )
        user2 = User(
            email="dup@example.com",
            name="User 2",
            auth_provider="apple",
            auth_provider_id="a-2",
        )
        db_session.add(user1)
        await db_session.commit()
        db_session.add(user2)

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestDBAthleteProfile:
    """Tests for the DBAthleteProfile ORM model."""

    async def test_create_profile(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Profile can be created with valid fields."""
        profile = DBAthleteProfile(
            user_id=test_user.id,
            name="Runner",
            age=25,
            weekly_mileage_base=40.0,
            goal_distance="10K",
            risk_tolerance="moderate",
        )
        db_session.add(profile)
        await db_session.commit()
        await db_session.refresh(profile)

        assert profile.id is not None
        assert profile.user_id == test_user.id
        assert profile.name == "Runner"
        assert profile.age == 25
        assert profile.training_days_per_week == 5  # default

    async def test_to_athlete_profile(self, test_profile: DBAthleteProfile) -> None:
        """to_athlete_profile() creates a frozen Pydantic snapshot."""
        snapshot = test_profile.to_athlete_profile()

        assert isinstance(snapshot, AthleteProfile)
        assert snapshot.name == "Test Runner"
        assert snapshot.age == 30
        assert snapshot.weekly_mileage_base == 30.0
        assert snapshot.goal_distance == "5K"
        assert snapshot.goal_time_minutes == 25.0
        assert snapshot.vdot == 40.0
        assert snapshot.risk_tolerance == RiskTolerance.MODERATE
        assert snapshot.training_days_per_week == 4
        assert snapshot.long_run_cap_pct == 0.30
        assert snapshot.max_weekly_increase_pct == 0.10

    async def test_to_athlete_profile_frozen(
        self, test_profile: DBAthleteProfile
    ) -> None:
        """Snapshot is frozen (immutable)."""
        snapshot = test_profile.to_athlete_profile()
        with pytest.raises(Exception):
            snapshot.age = 99

    async def test_to_athlete_profile_optional_fields(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Profile with all optional fields set converts correctly."""
        profile = DBAthleteProfile(
            user_id=test_user.id,
            name="Full Profile",
            age=35,
            vo2max=55.0,
            vdot=50.0,
            weekly_mileage_base=60.0,
            hr_max=185,
            hr_rest=50,
            injury_history="IT band 2024",
            risk_tolerance="conservative",
            max_weekly_increase_pct=0.05,
            goal_distance="marathon",
            goal_time_minutes=210.0,
            training_days_per_week=6,
            long_run_cap_pct=0.35,
        )
        db_session.add(profile)
        await db_session.commit()
        await db_session.refresh(profile)

        snapshot = profile.to_athlete_profile()
        assert snapshot.vo2max == 55.0
        assert snapshot.hr_max == 185
        assert snapshot.hr_rest == 50
        assert snapshot.injury_history == "IT band 2024"
        assert snapshot.risk_tolerance == RiskTolerance.CONSERVATIVE

    async def test_one_profile_per_user(
        self, db_session: AsyncSession, test_user: User, test_profile: DBAthleteProfile
    ) -> None:
        """Only one profile per user — unique constraint."""
        from sqlalchemy.exc import IntegrityError

        profile2 = DBAthleteProfile(
            user_id=test_user.id,
            name="Duplicate",
            age=25,
            weekly_mileage_base=20.0,
            goal_distance="5K",
        )
        db_session.add(profile2)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestTrainingPlan:
    """Tests for the TrainingPlan ORM model."""

    async def test_create_plan(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Plan can be created with JSONB fields."""
        plan = TrainingPlan(
            user_id=test_user.id,
            athlete_snapshot={"name": "Test", "age": 30},
            plan_data={"weeks": [{"number": 1, "workouts": []}]},
            decision_log=[{"iteration": 1, "outcome": "approved"}],
            scores={"safety": 85, "progression": 80},
            approved=True,
            total_tokens=5000,
            estimated_cost_usd=1.40,
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)

        assert plan.id is not None
        assert plan.approved is True
        assert plan.status == "active"
        assert plan.plan_data["weeks"][0]["number"] == 1

    async def test_plan_default_status(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Default status is 'active'."""
        plan = TrainingPlan(
            user_id=test_user.id,
            athlete_snapshot={},
            plan_data={},
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)
        assert plan.status == "active"


class TestWorkoutLog:
    """Tests for the WorkoutLog ORM model."""

    async def test_create_workout_log(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Workout log can be created."""
        log = WorkoutLog(
            user_id=test_user.id,
            actual_distance_km=10.0,
            actual_duration_minutes=55.0,
            avg_heart_rate=150,
            rpe=6,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.id is not None
        assert log.source == "manual"
        assert log.actual_distance_km == 10.0


class TestJob:
    """Tests for the Job ORM model."""

    async def test_create_job(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Job can be created with defaults."""
        job = Job(user_id=test_user.id)
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        assert job.id is not None
        assert job.status == "pending"
        assert job.job_type == "plan_generation"
        assert job.progress == []


class TestChatMessage:
    """Tests for the ChatMessage ORM model."""

    async def test_create_chat_message(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Chat message can be created linked to a plan."""
        plan = TrainingPlan(
            user_id=test_user.id,
            athlete_snapshot={},
            plan_data={},
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)

        msg = ChatMessage(
            plan_id=plan.id,
            user_id=test_user.id,
            role="user",
            content="Move my long run to Saturday",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.id is not None
        assert msg.role == "user"
        assert msg.change_type is None


class TestCascadeDeletes:
    """Tests for cascade delete behavior."""

    async def test_delete_user_cascades_to_profile(
        self, db_session: AsyncSession, test_user: User, test_profile: DBAthleteProfile
    ) -> None:
        """Deleting a user cascades to their profile."""
        await db_session.delete(test_user)
        await db_session.commit()

        result = await db_session.execute(
            select(DBAthleteProfile).where(
                DBAthleteProfile.user_id == test_user.id
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_user_cascades_to_plans(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Deleting a user cascades to their plans."""
        plan = TrainingPlan(
            user_id=test_user.id,
            athlete_snapshot={},
            plan_data={},
        )
        db_session.add(plan)
        await db_session.commit()

        await db_session.delete(test_user)
        await db_session.commit()

        result = await db_session.execute(
            select(TrainingPlan).where(TrainingPlan.user_id == test_user.id)
        )
        assert result.scalar_one_or_none() is None
