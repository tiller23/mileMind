"""Job manager — async plan generation with progress tracking.

Manages background plan generation tasks with SSE-compatible progress events.
Jobs are tracked in-memory (for active state) and persisted to the database
(for completion and event history).

Usage:
    manager = JobManager()
    job_id = await manager.start_plan_generation(user, profile, session_factory)
    events = manager.get_events(job_id, after=0)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.orchestrator import OrchestrationResult, Orchestrator
from src.agents.plan_postprocess import extract_structured_plan
from src.db.models import Job, TrainingPlan, User
from src.models.athlete import AthleteProfile
from src.models.plan_change import PlanChangeType
from src.models.progress import ProgressEvent, ProgressEventType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing constants (USD per token)
# Update these when Anthropic changes pricing.
# ---------------------------------------------------------------------------
SONNET_INPUT_COST_PER_TOKEN = 3.0 / 1_000_000   # $3/M input
SONNET_OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000  # $15/M output
OPUS_INPUT_COST_PER_TOKEN = 15.0 / 1_000_000     # $15/M input
OPUS_OUTPUT_COST_PER_TOKEN = 75.0 / 1_000_000    # $75/M output


# ---------------------------------------------------------------------------
# Active job state (in-memory)
# ---------------------------------------------------------------------------

@dataclass
class _ActiveJob:
    """In-memory state for a running job.

    Attributes:
        job_id: Database job ID.
        user_id: Owning user ID.
        events: Accumulated progress events.
        task: The asyncio task running the generation.
        done_event: Set when the job is complete.
    """

    job_id: uuid.UUID
    user_id: uuid.UUID
    events: list[ProgressEvent] = field(default_factory=list)
    task: asyncio.Task | None = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event)

    def add_event(self, event: ProgressEvent) -> None:
        """Add a progress event with auto-incrementing sequence.

        Args:
            event: The event to add.
        """
        event.sequence = len(self.events)
        self.events.append(event)


# ---------------------------------------------------------------------------
# Job Manager
# ---------------------------------------------------------------------------

class JobManager:
    """Manages async plan generation jobs with progress tracking.

    Singleton-style service. Tracks active jobs in memory with events
    list. Persists job status and events to database on completion.

    Note: In-memory state is per-process. Multi-worker deployments
    (uvicorn --workers > 1) will NOT share job state. Use a single
    async worker or migrate to Redis-backed state for production.

    Attributes:
        _active_jobs: Map of job_id -> active job state.
    """

    def __init__(self) -> None:
        self._active_jobs: dict[uuid.UUID, _ActiveJob] = {}

    async def start_plan_generation(
        self,
        user: User,
        athlete: AthleteProfile,
        session_factory: async_sessionmaker[AsyncSession],
        api_key: str | None = None,
        change_type: PlanChangeType = PlanChangeType.FULL,
        plan_start_date: date | None = None,
    ) -> uuid.UUID:
        """Start a background plan generation job.

        Creates a Job row, spawns an asyncio task running the orchestrator,
        and returns immediately with the job ID.

        Args:
            user: The authenticated user.
            athlete: The athlete profile to generate a plan for.
            session_factory: Async session factory for DB access in background.
            api_key: Anthropic API key (uses env default if None).
            change_type: Plan change scope (FULL/ADAPTATION/TWEAK).
            plan_start_date: When the plan should start (YYYY-MM-DD).

        Returns:
            The job ID for status polling and SSE streaming.
        """
        # C1 fix: Prevent concurrent jobs per user
        for active_job in self._active_jobs.values():
            if active_job.user_id == user.id and not active_job.done_event.is_set():
                raise ValueError(
                    "A plan generation job is already running for this user."
                )

        # Create job in database
        async with session_factory() as session:
            job = Job(user_id=user.id, job_type="plan_generation", status="pending")
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        # Set up in-memory tracking
        active = _ActiveJob(job_id=job_id, user_id=user.id)
        self._active_jobs[job_id] = active

        # Spawn background task
        active.task = asyncio.create_task(
            self._run_generation(
                active=active,
                athlete=athlete,
                session_factory=session_factory,
                api_key=api_key,
                change_type=change_type,
                plan_start_date=plan_start_date,
            ),
            name=f"plan-gen-{job_id}",
        )

        return job_id

    async def _run_generation(
        self,
        active: _ActiveJob,
        athlete: AthleteProfile,
        session_factory: async_sessionmaker[AsyncSession],
        api_key: str | None,
        change_type: PlanChangeType = PlanChangeType.FULL,
        plan_start_date: date | None = None,
    ) -> None:
        """Run the orchestrator with progress callbacks.

        This runs in a background asyncio task. On completion, persists
        the plan and updates the job status. Always cleans up in-memory
        state when done.

        Args:
            active: In-memory job state.
            athlete: Athlete profile.
            session_factory: Session factory for DB persistence.
            api_key: Anthropic API key.
            change_type: Plan change scope.
            plan_start_date: When the plan should start.
        """
        job_id = active.job_id

        try:
            # Mark running
            async with session_factory() as session:
                job = await session.get(Job, job_id)
                if job:
                    job.status = "running"
                    await session.commit()

            active.add_event(ProgressEvent(
                event_type=ProgressEventType.JOB_STARTED,
                message="Plan generation started",
            ))

            # Build orchestrator with progress callback
            def on_progress(event: ProgressEvent) -> None:
                active.add_event(event)

            orchestrator = Orchestrator(
                api_key=api_key,
                on_progress=on_progress,
            )

            result = await orchestrator.generate_plan(
                athlete, change_type=change_type, plan_start_date=plan_start_date,
            )

            # Persist plan to database
            await self._persist_result(
                active=active,
                athlete=athlete,
                result=result,
                session_factory=session_factory,
                plan_start_date=plan_start_date,
            )

        except Exception as e:
            logger.error("Plan generation failed for job %s: %s", job_id, e, exc_info=True)
            active.add_event(ProgressEvent(
                event_type=ProgressEventType.JOB_FAILED,
                message="Plan generation failed",
            ))
            active.done_event.set()

            # Mark job failed in DB (generic message for client safety)
            async with session_factory() as session:
                job = await session.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = "Plan generation failed. Please try again."
                    job.progress = [ev.to_dict() for ev in active.events]
                    job.completed_at = datetime.now(UTC)
                    await session.commit()

        finally:
            # Schedule cleanup after SSE clients have time to read final events
            asyncio.get_running_loop().call_later(
                60.0, self.cleanup, job_id,
            )

    async def _persist_result(
        self,
        active: _ActiveJob,
        athlete: AthleteProfile,
        result: OrchestrationResult,
        session_factory: async_sessionmaker[AsyncSession],
        plan_start_date: date | None = None,
    ) -> None:
        """Persist orchestration result to database.

        Creates a TrainingPlan row and updates the Job with completion status.

        Args:
            active: In-memory job state.
            athlete: Athlete profile (frozen snapshot).
            result: Orchestration result.
            session_factory: Session factory for DB access.
            plan_start_date: When the plan should start.
        """
        total_tokens = (
            result.total_planner_input_tokens + result.total_planner_output_tokens
            + result.total_reviewer_input_tokens + result.total_reviewer_output_tokens
        )
        # Cost estimate using per-model, per-direction pricing (per token)
        estimated_cost = (
            result.total_planner_input_tokens * SONNET_INPUT_COST_PER_TOKEN
            + result.total_planner_output_tokens * SONNET_OUTPUT_COST_PER_TOKEN
            + result.total_reviewer_input_tokens * OPUS_INPUT_COST_PER_TOKEN
            + result.total_reviewer_output_tokens * OPUS_OUTPUT_COST_PER_TOKEN
        )

        async with session_factory() as session:
            plan_data = extract_structured_plan(result.plan_text)
            if plan_start_date:
                plan_data["plan_start_date"] = plan_start_date.isoformat()
            plan = TrainingPlan(
                user_id=active.user_id,
                athlete_snapshot=athlete.model_dump(),
                plan_data=plan_data,
                decision_log=[
                    entry.model_dump(mode="json") for entry in result.decision_log
                ],
                scores=(
                    result.final_scores.model_dump() if result.final_scores else None
                ),
                approved=result.approved,
                status="active",
                total_tokens=total_tokens,
                estimated_cost_usd=round(estimated_cost, 4),
            )
            session.add(plan)
            await session.flush()
            plan_id = plan.id  # Capture before session exits

            # Update job
            job = await session.get(Job, active.job_id)
            if job:
                job.status = "complete"
                job.plan_id = plan_id
                job.progress = [ev.to_dict() for ev in active.events]
                job.completed_at = datetime.now(UTC)

            await session.commit()

        # Emit completion event
        active.add_event(ProgressEvent(
            event_type=ProgressEventType.JOB_COMPLETE,
            message="Plan generation complete",
            data={
                "plan_id": str(plan_id),
                "approved": result.approved,
                "total_tokens": total_tokens,
                "elapsed_seconds": round(result.total_elapsed_seconds, 1),
                "scores": (
                    result.final_scores.model_dump() if result.final_scores else None
                ),
            },
        ))
        active.done_event.set()

    def get_active_job_for_user(self, user_id: uuid.UUID) -> _ActiveJob | None:
        """Get the running job for a user, if any.

        Args:
            user_id: The user's ID.

        Returns:
            Active job state, or None if the user has no running job.
        """
        for active in self._active_jobs.values():
            if active.user_id == user_id and not active.done_event.is_set():
                return active
        return None

    def get_active_job(self, job_id: uuid.UUID) -> _ActiveJob | None:
        """Get in-memory state for an active job.

        Args:
            job_id: The job ID.

        Returns:
            Active job state, or None if not found or already cleaned up.
        """
        return self._active_jobs.get(job_id)

    def get_events(
        self,
        job_id: uuid.UUID,
        after: int = -1,
    ) -> list[ProgressEvent]:
        """Get progress events after a given sequence number.

        Args:
            job_id: The job ID.
            after: Return events with sequence > after. Default -1 returns all.

        Returns:
            List of new events, or empty list if job not found.
        """
        active = self._active_jobs.get(job_id)
        if active is None:
            return []
        return [e for e in active.events if e.sequence > after]

    def cleanup(self, job_id: uuid.UUID) -> None:
        """Remove completed job from in-memory tracking.

        Args:
            job_id: The job to clean up.
        """
        self._active_jobs.pop(job_id, None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_job_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    """Get or create the global JobManager singleton.

    Returns:
        The JobManager instance.
    """
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
