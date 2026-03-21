"""Tests for profile CRUD routes using FastAPI TestClient."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.db.models import DBAthleteProfile


class TestGetProfile:
    """Tests for GET /api/v1/profile."""

    async def test_no_profile_returns_404(self, client: AsyncClient) -> None:
        """Returns 404 when user has no profile."""
        resp = await client.get("/api/v1/profile")
        assert resp.status_code == 404

    async def test_get_existing_profile(
        self, client: AsyncClient, test_profile: DBAthleteProfile
    ) -> None:
        """Returns the user's profile."""
        resp = await client.get("/api/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Runner"
        assert data["age"] == 30
        assert data["goal_distance"] == "5K"


class TestUpsertProfile:
    """Tests for PUT /api/v1/profile."""

    async def test_create_profile(self, client: AsyncClient) -> None:
        """Creates a new profile when none exists."""
        profile_data = {
            "name": "New Runner",
            "age": 28,
            "weekly_mileage_base": 25.0,
            "goal_distance": "10K",
        }
        resp = await client.put("/api/v1/profile", json=profile_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Runner"
        assert data["age"] == 28
        assert data["risk_tolerance"] == "moderate"  # default

    async def test_update_profile(
        self, client: AsyncClient, test_profile: DBAthleteProfile
    ) -> None:
        """Updates an existing profile."""
        profile_data = {
            "name": "Updated Runner",
            "age": 31,
            "weekly_mileage_base": 35.0,
            "goal_distance": "half_marathon",
        }
        resp = await client.put("/api/v1/profile", json=profile_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Runner"
        assert data["age"] == 31
        assert data["goal_distance"] == "half_marathon"

    async def test_invalid_age_rejected(self, client: AsyncClient) -> None:
        """Age outside 10-100 is rejected."""
        profile_data = {
            "name": "Young",
            "age": 5,
            "weekly_mileage_base": 10.0,
            "goal_distance": "5K",
        }
        resp = await client.put("/api/v1/profile", json=profile_data)
        assert resp.status_code == 422

    async def test_invalid_risk_tolerance_rejected(self, client: AsyncClient) -> None:
        """Invalid risk tolerance value is rejected."""
        profile_data = {
            "name": "Test",
            "age": 30,
            "weekly_mileage_base": 30.0,
            "goal_distance": "5K",
            "risk_tolerance": "reckless",
        }
        resp = await client.put("/api/v1/profile", json=profile_data)
        assert resp.status_code == 422

    async def test_all_optional_fields(self, client: AsyncClient) -> None:
        """Profile with all optional fields set."""
        profile_data = {
            "name": "Full Profile",
            "age": 35,
            "vo2max": 55.0,
            "vdot": 50.0,
            "weekly_mileage_base": 60.0,
            "hr_max": 185,
            "hr_rest": 50,
            "injury_history": "IT band 2024",
            "risk_tolerance": "conservative",
            "max_weekly_increase_pct": 0.05,
            "goal_distance": "marathon",
            "goal_time_minutes": 210.0,
            "training_days_per_week": 6,
            "long_run_cap_pct": 0.35,
        }
        resp = await client.put("/api/v1/profile", json=profile_data)
        assert resp.status_code == 200
        data = resp.json()
        assert data["vo2max"] == 55.0
        assert data["hr_max"] == 185
        assert data["injury_history"] == "IT band 2024"
