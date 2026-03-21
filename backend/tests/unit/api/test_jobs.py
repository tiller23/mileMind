"""Tests for job routes — status polling and SSE streaming."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Job, User


pytestmark = pytest.mark.asyncio


class TestGetJobStatus:
    """Tests for GET /api/v1/jobs/{job_id}."""

    async def test_returns_404_for_nonexistent_job(self, client: AsyncClient):
        """Unknown job_id returns 404."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/jobs/{fake_id}")
        assert resp.status_code == 404

    async def test_returns_job_from_database(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User,
    ):
        """Returns job status from database for completed jobs."""
        job = Job(
            user_id=test_user.id,
            job_type="plan_generation",
            status="complete",
            progress=[{"event_type": "job_complete", "message": "done"}],
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        resp = await client.get(f"/api/v1/jobs/{job.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["job_id"] == str(job.id)
        assert len(data["progress"]) == 1

    async def test_returns_404_for_other_users_job(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Cannot access another user's job."""
        other_user_id = uuid.uuid4()
        job = Job(
            user_id=other_user_id,
            job_type="plan_generation",
            status="running",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        resp = await client.get(f"/api/v1/jobs/{job.id}")
        assert resp.status_code == 404


class TestStreamJobEvents:
    """Tests for GET /api/v1/jobs/{job_id}/stream."""

    async def test_returns_404_for_nonexistent_job(self, client: AsyncClient):
        """Unknown job_id returns 404."""
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/jobs/{fake_id}/stream")
        assert resp.status_code == 404

    async def test_returns_410_for_completed_job(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User,
    ):
        """Completed jobs return 410 Gone (use GET for final status)."""
        job = Job(
            user_id=test_user.id,
            job_type="plan_generation",
            status="complete",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        resp = await client.get(f"/api/v1/jobs/{job.id}/stream")
        assert resp.status_code == 410
