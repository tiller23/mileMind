"""Tests for public demo API routes."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TrainingPlan, User
from src.demo.constants import DEMO_PLAN_IDS, DEMO_USER_ID


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def demo_user(db_session: AsyncSession) -> User:
    """Create the demo user."""
    user = User(
        id=DEMO_USER_ID,
        email="demo@milemind.app",
        name="Demo User",
        auth_provider="demo",
        auth_provider_id="demo",
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def demo_plan(db_session: AsyncSession, demo_user: User) -> TrainingPlan:
    """Create a demo plan."""
    plan = TrainingPlan(
        id=DEMO_PLAN_IDS["beginner_5k"],
        user_id=DEMO_USER_ID,
        athlete_snapshot={"name": "Sarah Chen", "age": 28},
        plan_data={
            "goal_event": "5K",
            "weeks": [{"week_number": 1, "phase": "base", "workouts": []}],
            "notes": "Demo plan",
        },
        decision_log=[
            {
                "iteration": 1,
                "timestamp": "2026-03-22T14:30:00Z",
                "outcome": "approved",
                "scores": {"safety": 88, "progression": 85, "specificity": 82, "feasibility": 90, "overall": 86.6},
                "critique": "Good plan.",
                "issues": [],
                "planner_input_tokens": 2800,
                "planner_output_tokens": 3200,
                "reviewer_input_tokens": 4100,
                "reviewer_output_tokens": 850,
                "planner_tool_calls": 3,
                "reviewer_tool_calls": 2,
            }
        ],
        scores={"safety": 88, "progression": 85, "specificity": 82, "feasibility": 90, "overall": 86.6},
        approved=True,
        total_tokens=10950,
        estimated_cost_usd=1.42,
    )
    db_session.add(plan)
    await db_session.commit()
    return plan


class TestDemoRoutes:
    """Tests for /api/v1/demo/* endpoints."""

    async def test_list_demo_plans(self, client: AsyncClient, demo_plan: TrainingPlan) -> None:
        """GET /demo/plans returns demo plans without auth."""
        resp = await client.get("/api/v1/demo/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["goal_event"] == "5K"

    async def test_get_demo_plan(self, client: AsyncClient, demo_plan: TrainingPlan) -> None:
        """GET /demo/plans/{id} returns plan detail without auth."""
        resp = await client.get(f"/api/v1/demo/plans/{demo_plan.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_data"]["goal_event"] == "5K"
        assert data["approved"] is True

    async def test_get_demo_plan_debug(self, client: AsyncClient, demo_plan: TrainingPlan) -> None:
        """GET /demo/plans/{id}/debug returns debug view without auth."""
        resp = await client.get(f"/api/v1/demo/plans/{demo_plan.id}/debug")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["decision_log"]) == 1
        assert data["scores"]["safety"] == 88
        assert data["total_tokens"] == 10950

    async def test_non_demo_plan_returns_404(self, client: AsyncClient, demo_user: User) -> None:
        """Attempting to access a non-demo plan returns 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/demo/plans/{fake_id}")
        assert resp.status_code == 404

    async def test_list_empty_when_no_demo_data(self, client: AsyncClient) -> None:
        """Returns empty list when no demo plans exist."""
        resp = await client.get("/api/v1/demo/plans")
        assert resp.status_code == 200
        assert resp.json() == []
