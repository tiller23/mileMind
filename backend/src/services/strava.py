"""Strava API service — OAuth, activity import, and token management.

Handles all communication with the Strava v3 API: token exchange,
refresh, activity fetching, and import into WorkoutLog.

Usage:
    service = StravaService(settings, session)
    url = service.get_authorization_url(redirect_uri, state)
    token_data = await service.exchange_code(code, redirect_uri)
    count = await service.import_activities(user_id)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.db.models import StravaToken, WorkoutLog
from src.services.crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strava API constants
# ---------------------------------------------------------------------------

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
STRAVA_DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

# Import window: fetch activities from the last 75 days on first sync
IMPORT_WINDOW_DAYS = 75

# Buffer before expiry to trigger refresh (5 minutes)
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)

# Smart sync: overlap buffer to catch activities finalized after last sync
SYNC_OVERLAP_BUFFER = timedelta(hours=1)

# Safety limit on pagination to prevent infinite loops
MAX_PAGES = 20

# HTTP timeout for all Strava API calls (seconds)
HTTP_TIMEOUT = httpx.Timeout(30.0)


# ---------------------------------------------------------------------------
# Internal models
# ---------------------------------------------------------------------------

class StravaTokenData(BaseModel):
    """Token data returned from Strava token exchange or refresh.

    Attributes:
        access_token: Short-lived access token.
        refresh_token: Long-lived refresh token.
        expires_at: Unix timestamp when access token expires.
        athlete_id: Strava's athlete ID.
    """

    access_token: str
    refresh_token: str
    expires_at: int
    athlete_id: int


class StravaActivity(BaseModel):
    """A single Strava activity (running only).

    Attributes:
        id: Strava activity ID.
        name: Activity name.
        sport_type: Strava sport type (e.g., 'Run', 'TrailRun').
        distance: Distance in meters.
        moving_time: Moving time in seconds.
        start_date: Activity start time (UTC ISO string).
        average_heartrate: Average HR during activity (optional).
    """

    id: int
    name: str
    sport_type: str
    distance: float
    moving_time: int
    start_date: str
    average_heartrate: float | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class StravaService:
    """Service for Strava API communication and activity management.

    Args:
        settings: App settings with Strava client credentials.
        session: Async database session.
    """

    def __init__(self, settings: Settings, session: AsyncSession) -> None:
        self._settings = settings
        self._session = session

    @staticmethod
    def get_authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
        """Build the Strava OAuth authorization URL.

        Args:
            client_id: Strava application client ID.
            redirect_uri: URL Strava will redirect to after authorization.
            state: CSRF state parameter.

        Returns:
            Full authorization URL to redirect the user to.
        """
        return (
            f"{STRAVA_AUTH_URL}?"
            f"client_id={quote(client_id)}"
            f"&redirect_uri={quote(redirect_uri)}"
            f"&response_type=code"
            f"&scope=activity:read_all"
            f"&approval_prompt=auto"
            f"&state={quote(state)}"
        )

    async def exchange_code(self, code: str) -> StravaTokenData:
        """Exchange an authorization code for Strava tokens.

        Args:
            code: Authorization code from Strava OAuth callback.

        Returns:
            StravaTokenData with access/refresh tokens and athlete ID.

        Raises:
            httpx.HTTPStatusError: If Strava returns a non-200 response.
        """
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": self._settings.strava_client_id,
                    "client_secret": self._settings.strava_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return StravaTokenData(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            athlete_id=data["athlete"]["id"],
        )

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt a token if encryption is configured, otherwise return as-is.

        Args:
            ciphertext: Encrypted or plaintext token.

        Returns:
            Plaintext token.
        """
        key = self._settings.strava_token_encryption_key
        if key:
            return decrypt_token(ciphertext, key)
        return ciphertext

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a token if encryption is configured, otherwise return as-is.

        Args:
            plaintext: Token value.

        Returns:
            Encrypted or plaintext token.
        """
        key = self._settings.strava_token_encryption_key
        if key:
            return encrypt_token(plaintext, key)
        return plaintext

    async def refresh_token(self, strava_token: StravaToken) -> StravaToken:
        """Refresh an expired Strava access token.

        Updates the StravaToken row in the database with fresh credentials.

        Args:
            strava_token: The expired StravaToken ORM instance.

        Returns:
            The updated StravaToken with fresh access_token and expires_at.

        Raises:
            httpx.HTTPStatusError: If Strava refresh fails.
        """
        # Decrypt current refresh token for Strava API call
        decrypted_refresh = self._decrypt(strava_token.refresh_token)

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                STRAVA_TOKEN_URL,
                data={
                    "client_id": self._settings.strava_client_id,
                    "client_secret": self._settings.strava_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": decrypted_refresh,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Re-encrypt new tokens before storing
        strava_token.access_token = self._encrypt(data["access_token"])
        strava_token.refresh_token = self._encrypt(data["refresh_token"])
        strava_token.expires_at = datetime.fromtimestamp(
            data["expires_at"], tz=timezone.utc
        )
        await self._session.commit()
        return strava_token

    async def ensure_valid_token(self, user_id: uuid.UUID) -> tuple[StravaToken, str]:
        """Load the user's Strava token, refreshing if expired.

        Args:
            user_id: The user's ID.

        Returns:
            Tuple of (StravaToken ORM instance, decrypted access token string).

        Raises:
            ValueError: If the user has no Strava connection.
            httpx.HTTPStatusError: If token refresh fails.
        """
        result = await self._session.execute(
            select(StravaToken).where(StravaToken.user_id == user_id)
        )
        token = result.scalar_one_or_none()
        if token is None:
            raise ValueError("Strava not connected")

        now = datetime.now(timezone.utc)
        if token.expires_at <= now + TOKEN_REFRESH_BUFFER:
            logger.info("Refreshing expired Strava token for user %s", user_id)
            token = await self.refresh_token(token)

        return token, self._decrypt(token.access_token)

    async def fetch_activities(
        self,
        access_token: str,
        after: datetime | None = None,
        per_page: int = 50,
    ) -> list[StravaActivity]:
        """Fetch running activities from Strava.

        Paginates through all activities after the given date and filters
        to running-type activities only.

        Args:
            access_token: Valid Strava access token.
            after: Only fetch activities after this time. Defaults to 75 days ago.
            per_page: Page size for Strava API (max 200).

        Returns:
            List of running activities.
        """
        if after is None:
            after = datetime.now(timezone.utc) - timedelta(days=IMPORT_WINDOW_DAYS)

        after_epoch = int(after.timestamp())
        activities: list[StravaActivity] = []
        page = 1

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            while True:
                resp = await client.get(
                    STRAVA_ACTIVITIES_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "after": after_epoch,
                        "per_page": per_page,
                        "page": page,
                    },
                )
                resp.raise_for_status()
                page_data = resp.json()

                if not page_data:
                    break

                for item in page_data:
                    sport = item.get("sport_type", item.get("type", ""))
                    if sport in ("Run", "TrailRun", "VirtualRun"):
                        activities.append(StravaActivity(
                            id=item["id"],
                            name=item.get("name", ""),
                            sport_type=sport,
                            distance=item.get("distance", 0.0),
                            moving_time=item.get("moving_time", 0),
                            start_date=item.get("start_date", ""),
                            average_heartrate=item.get("average_heartrate"),
                        ))

                if len(page_data) < per_page:
                    break
                page += 1
                if page > MAX_PAGES:
                    logger.warning("Hit max page limit (%d) fetching activities", MAX_PAGES)
                    break

        return activities

    async def import_activities(self, user_id: uuid.UUID) -> tuple[int, int]:
        """Import Strava activities into WorkoutLog.

        Fetches recent running activities, deduplicates by strava_activity_id,
        and inserts new entries into the workout_logs table.

        Args:
            user_id: The user's ID.

        Returns:
            Tuple of (newly_imported_count, total_fetched_count).

        Raises:
            ValueError: If the user has no Strava connection.
        """
        token, access_token = await self.ensure_valid_token(user_id)

        # Smart sync: if we have prior imports, only fetch since the latest one
        last_import = await self._session.execute(
            select(func.max(WorkoutLog.completed_at)).where(
                WorkoutLog.user_id == user_id,
                WorkoutLog.source == "strava",
            )
        )
        last_date = last_import.scalar_one_or_none()
        # Subtract buffer to catch activities finalized after last sync
        if last_date is not None:
            last_date = last_date - SYNC_OVERLAP_BUFFER
        activities = await self.fetch_activities(access_token, after=last_date)

        if not activities:
            return 0, 0

        # Get existing strava_activity_ids for dedup
        strava_ids = [a.id for a in activities]
        result = await self._session.execute(
            select(WorkoutLog.strava_activity_id).where(
                WorkoutLog.user_id == user_id,
                WorkoutLog.strava_activity_id.in_(strava_ids),
            )
        )
        existing_ids = {row[0] for row in result.all()}

        imported = 0
        for activity in activities:
            if activity.id in existing_ids:
                continue

            # Convert: meters → km, seconds → minutes
            distance_km = round(activity.distance / 1000.0, 2)
            duration_min = round(activity.moving_time / 60.0, 1)

            # Parse start_date (Strava returns ISO 8601 UTC)
            try:
                completed_at = datetime.fromisoformat(
                    activity.start_date.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                completed_at = datetime.now(timezone.utc)

            log = WorkoutLog(
                user_id=user_id,
                source="strava",
                strava_activity_id=activity.id,
                actual_distance_km=distance_km,
                actual_duration_minutes=duration_min,
                avg_heart_rate=(
                    int(activity.average_heartrate)
                    if activity.average_heartrate
                    else None
                ),
                notes=activity.name,
                completed_at=completed_at,
            )
            self._session.add(log)
            imported += 1

        if imported > 0:
            await self._session.commit()

        return imported, len(activities)

    async def estimate_weekly_mileage(
        self,
        user_id: uuid.UUID,
        weeks: int = 4,
    ) -> float | None:
        """Estimate average weekly mileage from Strava activity logs.

        Args:
            user_id: The user's ID.
            weeks: Number of recent weeks to average over.

        Returns:
            Average weekly distance in km, or None if insufficient data.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        result = await self._session.execute(
            select(func.sum(WorkoutLog.actual_distance_km)).where(
                WorkoutLog.user_id == user_id,
                WorkoutLog.source == "strava",
                WorkoutLog.completed_at >= cutoff,
            )
        )
        total_km = result.scalar_one_or_none()
        if total_km is None or total_km == 0:
            return None

        return round(total_km / weeks, 1)

    async def disconnect(self, user_id: uuid.UUID) -> None:
        """Disconnect Strava — delete token and revoke on Strava's side.

        Args:
            user_id: The user's ID.
        """
        result = await self._session.execute(
            select(StravaToken).where(StravaToken.user_id == user_id)
        )
        token = result.scalar_one_or_none()
        if token is None:
            return

        # Best-effort revocation on Strava
        try:
            decrypted_access = self._decrypt(token.access_token)
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                await client.post(
                    STRAVA_DEAUTH_URL,
                    data={"access_token": decrypted_access},
                )
        except Exception:
            logger.warning(
                "Failed to revoke Strava token for user %s (best-effort)",
                user_id,
            )

        await self._session.execute(
            delete(StravaToken).where(StravaToken.user_id == user_id)
        )
        await self._session.commit()
