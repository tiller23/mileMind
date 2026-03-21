"""Job routes — status polling and SSE streaming for async plan generation.

Usage:
    POST /api/v1/plans/generate — triggers plan generation, returns job_id
    GET /api/v1/jobs/{job_id} — poll job status
    GET /api/v1/jobs/{job_id}/stream — SSE event stream
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.api.jobs import get_job_manager
from src.api.schemas import JobDetailResponse
from src.db.models import Job, User

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Maximum SSE stream duration (5 minutes). Plan generation typically
# takes 30-120s; this prevents orphaned connections.
_SSE_TIMEOUT_SECONDS = 300


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_status(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    """Get current status of an async job.

    Args:
        job_id: Job identifier.
        user: Authenticated user.
        session: Database session.

    Returns:
        JobDetailResponse with current status and progress.

    Raises:
        HTTPException: 404 if job not found or doesn't belong to user.
    """
    # Check in-memory first for active jobs
    manager = get_job_manager()
    active = manager.get_active_job(job_id)
    if active is not None and active.user_id == user.id:
        job_status = "running" if not active.done_event.is_set() else "complete"
        created_at = (
            active.events[0].timestamp
            if active.events
            else datetime.now(timezone.utc)
        )
        return JobDetailResponse(
            job_id=job_id,
            status=job_status,
            progress=[e.to_dict() for e in active.events],
            created_at=created_at,
        )

    # Fall back to database
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return JobDetailResponse(
        job_id=job.id,
        status=job.status,
        plan_id=job.plan_id,
        error=job.error,
        progress=job.progress or [],
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/stream")
async def stream_job_events(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream progress events via Server-Sent Events.

    Connects to the in-memory event stream for an active job.
    Sends events as they arrive, then closes when the job completes
    or when the timeout is reached.

    Args:
        job_id: Job identifier.
        user: Authenticated user.
        session: Database session.

    Returns:
        StreamingResponse with text/event-stream content type.

    Raises:
        HTTPException: 404 if job not found.
        HTTPException: 410 if job already completed (use GET for final status).
    """
    manager = get_job_manager()
    active = manager.get_active_job(job_id)

    # Check ownership first (before any DB query)
    if active is not None and active.user_id != user.id:
        active = None  # Treat as not found

    if active is None:
        # Check if it exists in DB (already completed)
        result = await session.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user.id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Job already completed. Use GET /jobs/{job_id} for final status.",
        )

    async def event_generator():
        """Yield SSE-formatted events as they arrive.

        Yields:
            SSE-formatted strings.
        """
        last_seq = -1
        deadline = time.monotonic() + _SSE_TIMEOUT_SECONDS
        poll_interval = 0.5

        while time.monotonic() < deadline:
            # Get new events
            new_events = manager.get_events(job_id, after=last_seq)
            for event in new_events:
                last_seq = event.sequence
                data = json.dumps(event.to_dict())
                yield f"event: {event.event_type.value}\ndata: {data}\n\n"

                # If job is done, send final event and close
                if event.event_type.value in ("job_complete", "job_failed"):
                    return

            # If done event is set but we haven't seen the terminal event,
            # do one more check then exit
            if active.done_event.is_set():
                new_events = manager.get_events(job_id, after=last_seq)
                for event in new_events:
                    last_seq = event.sequence
                    data = json.dumps(event.to_dict())
                    yield f"event: {event.event_type.value}\ndata: {data}\n\n"
                return

            # Poll interval
            await asyncio.sleep(poll_interval)

        # Timeout reached
        yield f"event: timeout\ndata: {json.dumps({'message': 'Stream timeout'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
