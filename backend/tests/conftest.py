"""Shared test fixtures for the MileMind backend test suite."""

import pytest

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
