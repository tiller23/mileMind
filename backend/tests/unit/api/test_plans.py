"""Tests for plan routes — list, get, debug, archive."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TrainingPlan, User


@pytest.fixture
async def test_plan(db_session: AsyncSession, test_user: User) -> TrainingPlan:
    """Create a test training plan.

    Args:
        db_session: Database session.
        test_user: Owning user.

    Returns:
        TrainingPlan ORM instance.
    """
    plan = TrainingPlan(
        user_id=test_user.id,
        athlete_snapshot={"name": "Test Runner", "age": 30},
        plan_data={"weeks": [{"number": 1, "workouts": [{"type": "easy", "km": 5}]}]},
        decision_log=[{"iteration": 1, "outcome": "approved", "scores": {"safety": 85}}],
        scores={"safety": 85, "progression": 80, "specificity": 75, "feasibility": 82},
        approved=True,
        total_tokens=5000,
        estimated_cost_usd=1.40,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


class TestListPlans:
    """Tests for GET /api/v1/plans."""

    async def test_empty_list(self, client: AsyncClient) -> None:
        """Returns empty list when user has no plans."""
        resp = await client.get("/api/v1/plans")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_plans(
        self, client: AsyncClient, test_plan: TrainingPlan
    ) -> None:
        """Returns list of plan summaries."""
        resp = await client.get("/api/v1/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["approved"] is True
        assert data[0]["status"] == "active"
        assert data[0]["scores"] is not None


class TestGetPlan:
    """Tests for GET /api/v1/plans/{plan_id}."""

    async def test_get_plan(
        self, client: AsyncClient, test_plan: TrainingPlan
    ) -> None:
        """Returns full plan detail."""
        resp = await client.get(f"/api/v1/plans/{test_plan.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_data"]["weeks"][0]["number"] == 1
        assert data["athlete_snapshot"]["name"] == "Test Runner"
        assert data["total_tokens"] == 5000

    async def test_plan_not_found(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent plan."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/plans/{fake_id}")
        assert resp.status_code == 404

    async def test_other_user_plan_not_visible(
        self, db_session: AsyncSession, client: AsyncClient
    ) -> None:
        """Plans belonging to other users return 404."""
        other_user = User(
            email="other@example.com",
            name="Other",
            auth_provider="google",
            auth_provider_id="g-other",
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        plan = TrainingPlan(
            user_id=other_user.id,
            athlete_snapshot={},
            plan_data={},
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)

        resp = await client.get(f"/api/v1/plans/{plan.id}")
        assert resp.status_code == 404


class TestGetPlanDebug:
    """Tests for GET /api/v1/plans/{plan_id}/debug."""

    async def test_get_debug_view(
        self, client: AsyncClient, test_plan: TrainingPlan
    ) -> None:
        """Returns debug info with decision log."""
        resp = await client.get(f"/api/v1/plans/{test_plan.id}/debug")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["decision_log"]) == 1
        assert data["scores"]["safety"] == 85
        assert data["total_tokens"] == 5000


class TestArchivePlan:
    """Tests for POST /api/v1/plans/{plan_id}/archive."""

    async def test_archive_plan(
        self, client: AsyncClient, test_plan: TrainingPlan
    ) -> None:
        """Archives a plan and updates its status."""
        resp = await client.post(f"/api/v1/plans/{test_plan.id}/archive")
        assert resp.status_code == 200

        # Verify status changed
        resp2 = await client.get(f"/api/v1/plans/{test_plan.id}")
        assert resp2.json()["status"] == "archived"

    async def test_archive_nonexistent(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent plan."""
        resp = await client.post(f"/api/v1/plans/{uuid.uuid4()}/archive")
        assert resp.status_code == 404
