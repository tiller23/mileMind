"""Strava integration routes — connect, sync, disconnect.

Handles Strava OAuth connection (not login), activity import,
and connection management. All routes require authentication.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.api.schemas import (
    MessageResponse,
    StravaCallbackRequest,
    StravaCallbackResponse,
    StravaConnectResponse,
    StravaStatusResponse,
    StravaSyncResponse,
    WorkoutLogResponse,
)
from src.config import Settings, get_settings
from src.db.models import StravaToken, User, WorkoutLog
from src.services.strava import StravaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strava", tags=["strava"])

# Minimum seconds between syncs to avoid hammering Strava API
_SYNC_COOLDOWN_SECONDS = 300  # 5 minutes


def _require_strava_configured(settings: Settings) -> None:
    """Raise 501 if Strava credentials are not configured.

    Args:
        settings: App settings.

    Raises:
        HTTPException: 501 if strava_client_id is empty.
    """
    if not settings.strava_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Strava integration not configured",
        )


@router.get("/connect", response_model=StravaConnectResponse)
async def strava_connect(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> StravaConnectResponse:
    """Return the Strava OAuth authorization URL.

    Generates a CSRF state token signed as a short-lived JWT,
    builds the authorization URL, and returns both to the frontend.

    Args:
        user: Authenticated user.
        settings: App settings with Strava client ID.

    Returns:
        Dict with auth_url, state (raw), and state_token (JWT-signed).
    """
    _require_strava_configured(settings)

    redirect_uri = f"{settings.frontend_url}/auth/callback/strava"
    state_raw = secrets.token_urlsafe(32)

    state_token = jwt.encode(
        {
            "state": state_raw,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
            "type": "strava_oauth_state",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    auth_url = StravaService.get_authorization_url(
        settings.strava_client_id, redirect_uri, state_raw,
    )

    return StravaConnectResponse(
        auth_url=auth_url,
        state=state_raw,
        state_token=state_token,
    )


@router.post("/callback", response_model=StravaCallbackResponse)
async def strava_callback(
    data: StravaCallbackRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StravaCallbackResponse:
    """Exchange Strava authorization code for tokens and store them.

    Verifies the CSRF state JWT, exchanges the code with Strava,
    and upserts a StravaToken row for the user.

    Args:
        data: Request body with authorization code and state JWT.
        user: Authenticated user.
        session: Database session.
        settings: App settings.

    Returns:
        Dict with connected status and athlete ID.

    Raises:
        HTTPException: 400 if state is invalid or code exchange fails.
    """
    _require_strava_configured(settings)

    # Verify CSRF state token
    try:
        payload = jwt.decode(
            data.state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "strava_oauth_state":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth state token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state token",
        )

    # Exchange code for tokens
    service = StravaService(settings, session)
    try:
        token_data = await service.exchange_code(data.code)
    except Exception:
        logger.exception("Strava token exchange failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code with Strava",
        )

    # Upsert StravaToken
    result = await session.execute(
        select(StravaToken).where(StravaToken.user_id == user.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.strava_athlete_id = token_data.athlete_id
        existing.access_token = token_data.access_token
        existing.refresh_token = token_data.refresh_token
        existing.expires_at = datetime.fromtimestamp(
            token_data.expires_at, tz=timezone.utc
        )
        existing.scope = "activity:read_all"
    else:
        token = StravaToken(
            user_id=user.id,
            strava_athlete_id=token_data.athlete_id,
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token,
            expires_at=datetime.fromtimestamp(
                token_data.expires_at, tz=timezone.utc
            ),
            scope="activity:read_all",
        )
        session.add(token)

    await session.commit()

    return StravaCallbackResponse(connected=True, athlete_id=token_data.athlete_id)


@router.get("/status", response_model=StravaStatusResponse)
async def strava_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StravaStatusResponse:
    """Get the user's Strava connection status.

    Args:
        user: Authenticated user.
        session: Database session.

    Returns:
        StravaStatusResponse with connected flag, athlete ID, and last sync time.
    """
    result = await session.execute(
        select(StravaToken).where(StravaToken.user_id == user.id)
    )
    token = result.scalar_one_or_none()

    if token is None:
        return StravaStatusResponse(connected=False)

    # Find the most recent Strava import timestamp
    last_sync_result = await session.execute(
        select(func.max(WorkoutLog.created_at)).where(
            WorkoutLog.user_id == user.id,
            WorkoutLog.source == "strava",
        )
    )
    last_sync = last_sync_result.scalar_one_or_none()

    return StravaStatusResponse(
        connected=True,
        athlete_id=token.strava_athlete_id,
        last_sync=last_sync,
    )


@router.post("/sync", response_model=StravaSyncResponse)
async def strava_sync(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StravaSyncResponse:
    """Import recent Strava activities into WorkoutLog.

    Fetches running activities from the last 75 days (first sync) or since
    last import (subsequent syncs), deduplicates,
    and stores them. Also estimates weekly mileage from the data.

    Args:
        user: Authenticated user.
        session: Database session.
        settings: App settings.

    Returns:
        StravaSyncResponse with import count and mileage suggestion.

    Raises:
        HTTPException: 404 if Strava not connected, 502 if Strava API fails.
    """
    _require_strava_configured(settings)

    # Cooldown: reject if synced too recently
    last_sync_result = await session.execute(
        select(func.max(WorkoutLog.created_at)).where(
            WorkoutLog.user_id == user.id,
            WorkoutLog.source == "strava",
        )
    )
    last_sync_time = last_sync_result.scalar_one_or_none()
    if last_sync_time is not None:
        elapsed = (datetime.now(timezone.utc) - last_sync_time).total_seconds()
        if elapsed < _SYNC_COOLDOWN_SECONDS:
            remaining = int(_SYNC_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before syncing again.",
            )

    service = StravaService(settings, session)

    try:
        imported_count, total_count = await service.import_activities(user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception:
        logger.exception("Strava activity import failed for user %s", user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch activities from Strava. Please try again.",
        )

    # Estimate weekly mileage from imported data
    suggested_mileage = await service.estimate_weekly_mileage(user.id)

    return StravaSyncResponse(
        imported_count=imported_count,
        total_activities=total_count,
        suggested_weekly_mileage_km=suggested_mileage,
    )


@router.post("/disconnect", response_model=MessageResponse)
async def strava_disconnect(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Disconnect Strava — remove token and revoke access.

    Args:
        user: Authenticated user.
        session: Database session.
        settings: App settings.

    Returns:
        Success message.
    """
    service = StravaService(settings, session)
    await service.disconnect(user.id)
    return MessageResponse(detail="Strava disconnected")


@router.get("/activities", response_model=list[WorkoutLogResponse])
async def strava_activities(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[WorkoutLogResponse]:
    """List the user's imported Strava activities.

    Args:
        user: Authenticated user.
        session: Database session.
        limit: Max number of activities to return (1-200).
        offset: Number of activities to skip.

    Returns:
        List of WorkoutLogResponse ordered by completed_at descending.
    """
    result = await session.execute(
        select(WorkoutLog)
        .where(
            WorkoutLog.user_id == user.id,
            WorkoutLog.source == "strava",
        )
        .order_by(WorkoutLog.completed_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = result.scalars().all()
    return [WorkoutLogResponse.model_validate(log) for log in logs]
