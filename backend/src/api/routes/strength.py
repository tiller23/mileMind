"""Strength playbook routes.

GET /strength/playbook returns a deterministic exercise playbook for the
authenticated user's profile, plus per-block LLM-generated rationale
narratives (with static fallbacks on API failure).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.api.rate_limit import limiter
from src.api.schemas import (
    AcuteGate,
    BlockOut,
    ExerciseOut,
    StrengthPlaybookResponse,
)
from src.config import Settings, get_settings
from src.db.models import DBAthleteProfile, User
from src.strength import build_playbook
from src.strength.narrative import generate_narrative

router = APIRouter(prefix="/strength", tags=["strength"])


@router.get("/playbook", response_model=StrengthPlaybookResponse)
@limiter.limit("30/minute")
async def get_playbook(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StrengthPlaybookResponse:
    """Return the current user's strength playbook.

    Args:
        request: Incoming request (required by the rate limiter).
        user: Authenticated user.
        session: Async database session.
        settings: App settings (for Anthropic API key).

    Returns:
        StrengthPlaybookResponse with acute-injury gate + block list.

    Raises:
        HTTPException: 404 if the user has no profile yet.
    """
    result = await session.execute(
        select(DBAthleteProfile).where(DBAthleteProfile.user_id == user.id)
    )
    profile_db = result.scalar_one_or_none()
    if profile_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Complete onboarding first.",
        )

    athlete = profile_db.to_athlete_profile()

    # Safety: when an acute injury is flagged, suppress exercise content
    # server-side. The UI shows a PT-referral gate; the API mirrors that
    # by returning no blocks so a direct API caller cannot bypass it.
    if athlete.current_acute_injury:
        return StrengthPlaybookResponse(
            acute_injury_gate=AcuteGate(
                active=True,
                description=athlete.current_injury_description,
            ),
            blocks=[],
            catalog_version="",
            profile_summary={"current_acute_injury": True},
        )

    playbook = build_playbook(athlete)
    narrative_map = await generate_narrative(
        playbook,
        athlete,
        api_key=settings.anthropic_api_key,
    )

    blocks_out = [
        BlockOut(
            block_id=b.block_id,
            title=b.title,
            rationale=narrative_map.get(b.block_id, b.rationale_fallback),
            exercises=[
                ExerciseOut(
                    id=e.id,
                    name=e.name,
                    equipment=list(e.equipment),
                    difficulty=e.difficulty,
                    search_query=e.search_query,
                )
                for e in b.exercises
            ],
            matched_injury_tags=list(b.matched_injury_tags),
        )
        for b in playbook.blocks
    ]

    return StrengthPlaybookResponse(
        acute_injury_gate=AcuteGate(
            active=athlete.current_acute_injury,
            description=athlete.current_injury_description,
        ),
        blocks=blocks_out,
        catalog_version=playbook.catalog_version,
        profile_summary=playbook.profile_summary,
    )
