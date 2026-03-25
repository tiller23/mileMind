"""Tests for POST /api/v1/plans/generate endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DBAthleteProfile, User


pytestmark = pytest.mark.asyncio


class TestGeneratePlan:
    """Tests for POST /api/v1/plans/generate."""

    async def test_returns_403_without_invite_code(
        self, client: AsyncClient
    ):
        """Generating a plan without an invite code returns 403."""
        resp = await client.post("/api/v1/plans/generate")
        assert resp.status_code == 403
        assert "Invite code required" in resp.json()["detail"]

    async def test_returns_404_without_profile(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Generating a plan without a profile returns 404."""
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()
        resp = await client.post("/api/v1/plans/generate")
        assert resp.status_code == 404
        assert "Profile not found" in resp.json()["detail"]

    async def test_returns_202_with_job_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_profile: DBAthleteProfile,
    ):
        """Valid request returns 202 with job_id."""
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()

        with patch("src.api.routes.plans.get_job_manager") as mock_mgr:
            mock_manager = AsyncMock()
            mock_job_id = uuid.uuid4()
            mock_manager.start_plan_generation = AsyncMock(return_value=mock_job_id)
            mock_mgr.return_value = mock_manager

            resp = await client.post("/api/v1/plans/generate")

        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"] == str(mock_job_id)
        assert data["status"] == "pending"

    async def test_passes_athlete_profile_to_manager(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_profile: DBAthleteProfile,
    ):
        """The endpoint constructs an AthleteProfile from the DB record."""
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()

        with patch("src.api.routes.plans.get_job_manager") as mock_mgr:
            mock_manager = AsyncMock()
            mock_manager.start_plan_generation = AsyncMock(return_value=uuid.uuid4())
            mock_mgr.return_value = mock_manager

            await client.post("/api/v1/plans/generate")

            call_kwargs = mock_manager.start_plan_generation.call_args
            athlete = call_kwargs.kwargs.get("athlete") or call_kwargs[1].get("athlete")
            assert athlete is not None
            assert athlete.name == "Test Runner"
            assert athlete.age == 30
            assert athlete.goal_distance == "5K"

    async def test_rejects_invalid_change_type(self, client: AsyncClient):
        """Invalid change_type returns 422."""
        resp = await client.post(
            "/api/v1/plans/generate",
            json={"change_type": "invalid"},
        )
        assert resp.status_code == 422
