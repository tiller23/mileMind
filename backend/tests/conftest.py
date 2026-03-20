"""Shared test fixtures for the MileMind backend test suite."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, DBAthleteProfile, User
from src.models.athlete import AthleteProfile, RiskTolerance


@pytest.fixture
def sample_athlete() -> AthleteProfile:
    """A simple beginner athlete for testing.

    Used across unit, integration, and e2e tests. Matches the profile
    used in integration/test_planner.py and integration/agents/test_reviewer.py.
    """
    return AthleteProfile(
        name="Test Runner",
        age=30,
        weekly_mileage_base=30.0,
        goal_distance="5K",
        goal_time_minutes=25.0,
        vdot=40.0,
        risk_tolerance=RiskTolerance.MODERATE,
        training_days_per_week=4,
    )


@pytest.fixture
async def async_engine():
    """Create an async SQLite engine for testing.

    Creates all tables from ORM metadata. Tears down after test.

    Yields:
        AsyncEngine backed by in-memory SQLite.
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine) -> AsyncSession:
    """Yield an async session for testing, rolled back after each test.

    Args:
        async_engine: The test engine fixture.

    Yields:
        AsyncSession.
    """
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database.

    Args:
        db_session: Async database session.

    Returns:
        User ORM instance.
    """
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="Test User",
        auth_provider="google",
        auth_provider_id="google-123",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_profile(db_session: AsyncSession, test_user: User) -> DBAthleteProfile:
    """Create a test athlete profile in the database.

    Args:
        db_session: Async database session.
        test_user: User who owns the profile.

    Returns:
        DBAthleteProfile ORM instance.
    """
    profile = DBAthleteProfile(
        user_id=test_user.id,
        name="Test Runner",
        age=30,
        weekly_mileage_base=30.0,
        goal_distance="5K",
        goal_time_minutes=25.0,
        vdot=40.0,
        risk_tolerance="moderate",
        training_days_per_week=4,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile
