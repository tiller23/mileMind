"""Profile CRUD routes — create/update/get athlete profile.

Each user has exactly one athlete profile (one-to-one).
PUT creates the profile if it doesn't exist, or updates it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.shared import sanitize_prompt_text
from src.api.deps import get_current_user, get_db
from src.api.schemas import ProfileResponse, ProfileUpdate
from src.db.models import DBAthleteProfile, User

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Get the current user's athlete profile.

    Args:
        user: Authenticated user.
        session: Database session.

    Returns:
        ProfileResponse with all profile fields.

    Raises:
        HTTPException: 404 if profile not found.
    """
    result = await session.execute(
        select(DBAthleteProfile).where(DBAthleteProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Complete onboarding first.",
        )
    return ProfileResponse.model_validate(profile)


@router.put("", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
async def upsert_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Create or update the current user's athlete profile.

    If the user already has a profile, updates it. Otherwise creates one.

    Args:
        data: Profile fields to set.
        user: Authenticated user.
        session: Database session.

    Returns:
        ProfileResponse with the saved profile.
    """
    # Sanitize free-text fields at the API boundary (defense-in-depth)
    sanitized = data.model_dump()
    sanitized["name"] = sanitize_prompt_text(sanitized["name"])
    sanitized["injury_history"] = sanitize_prompt_text(sanitized["injury_history"])
    sanitized["goal_distance"] = sanitize_prompt_text(sanitized["goal_distance"])

    result = await session.execute(
        select(DBAthleteProfile).where(DBAthleteProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = DBAthleteProfile(user_id=user.id, **sanitized)
        session.add(profile)
    else:
        for field_name, value in sanitized.items():
            setattr(profile, field_name, value)

    await session.commit()
    await session.refresh(profile)
    return ProfileResponse.model_validate(profile)
