"""Plan routes — list, get, generate, debug, archive.

Includes async plan generation via POST /plans/generate.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.api.deps import get_current_user, get_db
from src.api.jobs import get_job_manager
from src.api.schemas import (
    JobResponse,
    MessageResponse,
    PlanDebug,
    PlanDetail,
    PlanGenerateRequest,
    PlanSummary,
    PlanUpdateStartDate,
)
from src.config import get_settings
from src.db.models import DBAthleteProfile, TrainingPlan, User
from src.db.session import get_session_factory
from src.models.plan_change import PlanChangeType

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post(
    "/generate",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_plan(
    body: PlanGenerateRequest = PlanGenerateRequest(),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Trigger async plan generation.

    Reads the user's saved athlete profile, starts a background orchestrator
    job, and returns immediately with a job ID for polling/streaming.

    Args:
        body: Generation options (change_type).
        user: Authenticated user.
        session: Database session.

    Returns:
        JobResponse with job_id and status='pending'.

    Raises:
        HTTPException: 404 if user has no profile.
    """
    # Load athlete profile from DB
    result = await session.execute(
        select(DBAthleteProfile).where(DBAthleteProfile.user_id == user.id)
    )
    db_profile = result.scalar_one_or_none()
    if db_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Complete onboarding first.",
        )

    # Convert DB profile to domain model
    athlete = db_profile.to_athlete_profile()

    settings = get_settings()
    manager = get_job_manager()
    session_factory = get_session_factory()

    change_type = PlanChangeType(body.change_type)

    # Default plan_start_date to next Monday if not provided
    plan_start_date = body.plan_start_date
    if plan_start_date is None:
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        plan_start_date = today + timedelta(days=days_until_monday)

    try:
        job_id = await manager.start_plan_generation(
            user=user,
            athlete=athlete,
            session_factory=session_factory,
            api_key=settings.anthropic_api_key or None,
            change_type=change_type,
            plan_start_date=plan_start_date,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return JobResponse(job_id=job_id, status="pending")


@router.get("", response_model=list[PlanSummary])
async def list_plans(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[PlanSummary]:
    """List all training plans for the current user.

    Returns plans ordered by creation time, newest first.

    Args:
        user: Authenticated user.
        session: Database session.

    Returns:
        List of PlanSummary objects.
    """
    result = await session.execute(
        select(TrainingPlan)
        .where(TrainingPlan.user_id == user.id)
        .order_by(TrainingPlan.created_at.desc())
    )
    plans = result.scalars().all()
    summaries = []
    for p in plans:
        plan_data = p.plan_data or {}
        weeks = plan_data.get("weeks", [])
        summaries.append(PlanSummary(
            id=p.id,
            approved=p.approved,
            status=p.status,
            scores=p.scores,
            goal_event=plan_data.get("goal_event"),
            week_count=len(weeks) if weeks else None,
            created_at=p.created_at,
        ))
    return summaries


@router.get("/{plan_id}", response_model=PlanDetail)
async def get_plan(
    plan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Get full plan detail including plan data and decision log.

    Args:
        plan_id: Plan ID.
        user: Authenticated user.
        session: Database session.

    Returns:
        PlanDetail with all plan data.

    Raises:
        HTTPException: 404 if plan not found or doesn't belong to user.
    """
    result = await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user.id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    return PlanDetail.model_validate(plan)


@router.get("/{plan_id}/debug", response_model=PlanDebug)
async def get_plan_debug(
    plan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PlanDebug:
    """Get plan debug view with decision log and scores.

    Args:
        plan_id: Plan ID.
        user: Authenticated user.
        session: Database session.

    Returns:
        PlanDebug with decision log and scoring info.

    Raises:
        HTTPException: 404 if plan not found.
    """
    result = await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user.id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    return PlanDebug.model_validate(plan)


@router.patch(
    "/{plan_id}/start-date",
    response_model=PlanDetail,
    status_code=status.HTTP_200_OK,
)
async def update_plan_start_date(
    plan_id: uuid.UUID,
    body: PlanUpdateStartDate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Update a plan's start date to shift the training timeline.

    Adjusts when Week 1 begins without changing the plan content.
    Use this when a user needs to delay or advance their plan
    (e.g., vacation, missed days).

    Args:
        plan_id: Plan ID.
        body: New start date.
        user: Authenticated user.
        session: Database session.

    Returns:
        Updated PlanDetail.

    Raises:
        HTTPException: 404 if plan not found.
    """
    result = await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user.id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    updated_data = dict(plan.plan_data) if plan.plan_data else {}
    updated_data["plan_start_date"] = body.plan_start_date.isoformat()
    plan.plan_data = updated_data
    flag_modified(plan, "plan_data")
    await session.commit()
    await session.refresh(plan)
    return PlanDetail.model_validate(plan)


@router.post(
    "/{plan_id}/archive",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def archive_plan(
    plan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Archive a training plan.

    Args:
        plan_id: Plan ID to archive.
        user: Authenticated user.
        session: Database session.

    Returns:
        MessageResponse confirming archival.

    Raises:
        HTTPException: 404 if plan not found.
    """
    result = await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == user.id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    plan.status = "archived"
    await session.commit()
    return MessageResponse(detail="Plan archived")
