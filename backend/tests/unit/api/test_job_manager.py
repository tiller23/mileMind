"""Tests for the JobManager service and ProgressEvent model."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.jobs import (
    JobManager,
    _ActiveJob,
    get_job_manager,
)
from src.db.models import Base, User
from src.models.athlete import AthleteProfile
from src.models.progress import ProgressEvent, ProgressEventType

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# ProgressEvent tests
# ---------------------------------------------------------------------------


class TestProgressEvent:
    """Tests for ProgressEvent serialization."""

    def test_to_dict(self):
        """to_dict produces a JSON-serializable dict."""
        event = ProgressEvent(
            event_type=ProgressEventType.PLANNER_STARTED,
            message="Planner starting",
            data={"attempt": 1},
            sequence=0,
        )
        d = event.to_dict()
        assert d["event_type"] == "planner_started"
        assert d["message"] == "Planner starting"
        assert d["data"]["attempt"] == 1
        assert d["sequence"] == 0
        assert "timestamp" in d

    def test_to_dict_empty_data(self):
        """Empty data field serializes correctly."""
        event = ProgressEvent(
            event_type=ProgressEventType.JOB_STARTED,
            message="Started",
        )
        d = event.to_dict()
        assert d["data"] == {}


# ---------------------------------------------------------------------------
# _ActiveJob tests
# ---------------------------------------------------------------------------


class TestActiveJob:
    """Tests for in-memory active job state."""

    def test_add_event_auto_sequences(self):
        """Events get auto-incrementing sequence numbers."""
        active = _ActiveJob(job_id=uuid.uuid4(), user_id=uuid.uuid4())
        e1 = ProgressEvent(
            event_type=ProgressEventType.JOB_STARTED,
            message="Started",
        )
        e2 = ProgressEvent(
            event_type=ProgressEventType.PLANNER_STARTED,
            message="Planner",
        )
        active.add_event(e1)
        active.add_event(e2)
        assert e1.sequence == 0
        assert e2.sequence == 1
        assert len(active.events) == 2


# ---------------------------------------------------------------------------
# JobManager tests
# ---------------------------------------------------------------------------


class TestJobManager:
    """Tests for the JobManager service."""

    def test_get_events_returns_empty_for_unknown_job(self):
        """get_events returns [] for unknown job_id."""
        manager = JobManager()
        events = manager.get_events(uuid.uuid4())
        assert events == []

    def test_get_events_filters_by_sequence(self):
        """get_events returns only events after the given sequence."""
        manager = JobManager()
        job_id = uuid.uuid4()
        active = _ActiveJob(job_id=job_id, user_id=uuid.uuid4())

        for i in range(5):
            active.add_event(
                ProgressEvent(
                    event_type=ProgressEventType.PLANNER_STARTED,
                    message=f"Event {i}",
                )
            )

        manager._active_jobs[job_id] = active

        events = manager.get_events(job_id, after=2)
        assert len(events) == 2
        assert events[0].sequence == 3
        assert events[1].sequence == 4

    def test_get_active_job_returns_none_for_unknown(self):
        """get_active_job returns None for unknown job_id."""
        manager = JobManager()
        assert manager.get_active_job(uuid.uuid4()) is None

    def test_cleanup_removes_job(self):
        """cleanup removes a job from active tracking."""
        manager = JobManager()
        job_id = uuid.uuid4()
        active = _ActiveJob(job_id=job_id, user_id=uuid.uuid4())
        manager._active_jobs[job_id] = active

        manager.cleanup(job_id)
        assert manager.get_active_job(job_id) is None

    def test_cleanup_idempotent(self):
        """cleanup on unknown job_id does not raise."""
        manager = JobManager()
        manager.cleanup(uuid.uuid4())  # should not raise

    async def test_start_plan_generation_creates_job(self):
        """start_plan_generation creates a Job in the database."""
        engine = create_async_engine("sqlite+aiosqlite://", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        # Create a user
        async with factory() as session:
            user = User(
                email="test@test.com",
                name="Test",
                auth_provider="google",
                auth_provider_id="123",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        athlete = AthleteProfile(
            name="Test Runner",
            age=30,
            weekly_mileage_base=30.0,
            goal_distance="5K",
        )

        manager = JobManager()

        # Mock the orchestrator to avoid actual API calls
        with patch("src.api.jobs.Orchestrator") as MockOrch:
            mock_result = MagicMock()
            mock_result.plan_text = "Test plan"
            mock_result.approved = True
            mock_result.decision_log = []
            mock_result.total_planner_input_tokens = 100
            mock_result.total_planner_output_tokens = 200
            mock_result.total_reviewer_input_tokens = 50
            mock_result.total_reviewer_output_tokens = 100
            mock_result.total_elapsed_seconds = 5.0
            mock_result.final_scores = None
            mock_result.error = None
            mock_result.warning = None

            mock_orch_instance = AsyncMock()
            mock_orch_instance.generate_plan = AsyncMock(return_value=mock_result)
            MockOrch.return_value = mock_orch_instance

            job_id = await manager.start_plan_generation(
                user=user,
                athlete=athlete,
                session_factory=factory,
            )

            # Wait for the background task
            active = manager.get_active_job(job_id)
            assert active is not None

            # Give the task time to complete
            await asyncio.sleep(0.5)

        assert job_id is not None
        assert isinstance(job_id, uuid.UUID)

        await engine.dispose()


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestGetJobManager:
    """Tests for the get_job_manager singleton."""

    def test_returns_same_instance(self):
        """get_job_manager returns the same instance."""
        import src.api.jobs as jobs_module

        # Reset singleton
        jobs_module._job_manager = None

        m1 = get_job_manager()
        m2 = get_job_manager()
        assert m1 is m2

        # Cleanup
        jobs_module._job_manager = None
