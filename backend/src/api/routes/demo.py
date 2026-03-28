"""Public demo routes — browse pre-generated plans without authentication.

These endpoints serve demo plans that showcase MileMind's capabilities
for portfolio/resume visitors. No auth required.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.schemas import PlanDebug, PlanDetail, PlanSummary
from src.db.models import TrainingPlan
from src.demo.constants import DEMO_USER_ID

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/plans", response_model=list[PlanSummary])
async def list_demo_plans(
    session: AsyncSession = Depends(get_db),
) -> list[PlanSummary]:
    """List all demo plans.

    No authentication required. Returns only plans owned by the demo user.

    Args:
        session: Database session.

    Returns:
        List of demo plan summaries.
    """
    result = await session.execute(
        select(TrainingPlan)
        .where(TrainingPlan.user_id == DEMO_USER_ID)
        .order_by(TrainingPlan.created_at.desc())
    )
    plans = result.scalars().all()

    return [
        PlanSummary(
            id=p.id,
            goal_event=p.plan_data.get("goal_event", ""),
            week_count=len(p.plan_data.get("weeks", [])),
            approved=p.approved,
            status=p.status,
            estimated_cost_usd=p.estimated_cost_usd,
            created_at=p.created_at,
        )
        for p in plans
    ]


@router.get("/plans/{plan_id}", response_model=PlanDetail)
async def get_demo_plan(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> PlanDetail:
    """Get a demo plan's full detail.

    No authentication required. Only returns plans owned by the demo user.

    Args:
        plan_id: Demo plan identifier.
        session: Database session.

    Returns:
        Full plan detail.

    Raises:
        HTTPException: 404 if plan not found or not a demo plan.
    """
    result = await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == DEMO_USER_ID,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo plan not found",
        )

    return PlanDetail(
        id=plan.id,
        user_id=plan.user_id,
        athlete_snapshot=plan.athlete_snapshot,
        plan_data=plan.plan_data,
        decision_log=plan.decision_log,
        scores=plan.scores,
        approved=plan.approved,
        status=plan.status,
        total_tokens=plan.total_tokens,
        estimated_cost_usd=plan.estimated_cost_usd,
        created_at=plan.created_at,
    )


@router.get("/plans/{plan_id}/debug", response_model=PlanDebug)
async def get_demo_plan_debug(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> PlanDebug:
    """Get a demo plan's debug/transparency view.

    No authentication required. Only returns plans owned by the demo user.

    Args:
        plan_id: Demo plan identifier.
        session: Database session.

    Returns:
        Plan debug info with decision log and scores.

    Raises:
        HTTPException: 404 if plan not found or not a demo plan.
    """
    result = await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == DEMO_USER_ID,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo plan not found",
        )

    return PlanDebug(
        id=plan.id,
        decision_log=plan.decision_log,
        scores=plan.scores,
        approved=plan.approved,
        total_tokens=plan.total_tokens,
        estimated_cost_usd=plan.estimated_cost_usd,
    )
