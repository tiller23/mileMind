"""Plan routes — list, get, debug, archive.

Plan generation (POST + SSE) will be added in Phase 5b.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.api.schemas import PlanDebug, PlanDetail, PlanSummary
from src.db.models import TrainingPlan, User

router = APIRouter(prefix="/plans", tags=["plans"])


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
    return [PlanSummary.model_validate(p) for p in plans]


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


@router.post("/{plan_id}/archive", status_code=status.HTTP_200_OK)
async def archive_plan(
    plan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Archive a training plan.

    Args:
        plan_id: Plan ID to archive.
        user: Authenticated user.
        session: Database session.

    Returns:
        Success message.

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
    return {"detail": "Plan archived"}
