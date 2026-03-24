"""Unit tests for the Strava service layer.

Tests Strava API communication (mocked httpx), token management,
activity import with deduplication, and weekly mileage estimation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.db.models import StravaToken, WorkoutLog
from src.services.strava import (
    STRAVA_DEAUTH_URL,
    STRAVA_TOKEN_URL,
    StravaActivity,
    StravaService,
    StravaTokenData,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings with Strava credentials."""
    return Settings(
        strava_client_id="test-client-id",
        strava_client_secret="test-client-secret",
        jwt_secret="test-secret",
        debug=True,
    )


@pytest.fixture
def strava_token_row(test_user, db_session: AsyncSession) -> StravaToken:
    """Create a StravaToken in the database (not yet committed — caller commits)."""
    token = StravaToken(
        user_id=test_user.id,
        strava_athlete_id=12345,
        access_token="strava-access-token",
        refresh_token="strava-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        scope="activity:read_all",
    )
    return token


def _make_strava_token_response(
    access_token: str = "new-access",
    refresh_token: str = "new-refresh",
    expires_at: int = 9999999999,
    athlete_id: int = 12345,
) -> dict:
    """Build a mock Strava token exchange response."""
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "athlete": {"id": athlete_id},
    }


def _make_activity(
    activity_id: int = 1,
    sport_type: str = "Run",
    distance: float = 5000.0,
    moving_time: int = 1800,
    heartrate: float | None = 145.0,
) -> dict:
    """Build a mock Strava activity dict."""
    return {
        "id": activity_id,
        "name": f"Activity {activity_id}",
        "sport_type": sport_type,
        "distance": distance,
        "moving_time": moving_time,
        "start_date": "2026-03-20T08:00:00Z",
        "average_heartrate": heartrate,
    }


@pytest.mark.asyncio
class TestExchangeCode:
    """Tests for StravaService.exchange_code."""

    async def test_success(self, settings: Settings, db_session: AsyncSession) -> None:
        """Successful code exchange returns StravaTokenData."""
        service = StravaService(settings, db_session)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_strava_token_response()
        mock_resp.raise_for_status = MagicMock()

        with patch("src.services.strava.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.exchange_code("auth-code")

        assert isinstance(result, StravaTokenData)
        assert result.access_token == "new-access"
        assert result.athlete_id == 12345

    async def test_failure_raises(self, settings: Settings, db_session: AsyncSession) -> None:
        """Failed code exchange propagates HTTP error."""
        service = StravaService(settings, db_session)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock()
        )

        with patch("src.services.strava.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await service.exchange_code("bad-code")


@pytest.mark.asyncio
class TestRefreshToken:
    """Tests for StravaService.refresh_token."""

    async def test_updates_db(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
        strava_token_row,
    ) -> None:
        """Refresh updates the StravaToken row with new credentials."""
        db_session.add(strava_token_row)
        await db_session.commit()

        service = StravaService(settings, db_session)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "refreshed-access",
            "refresh_token": "refreshed-refresh",
            "expires_at": 9999999999,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("src.services.strava.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.refresh_token(strava_token_row)

        assert result.access_token == "refreshed-access"
        assert result.refresh_token == "refreshed-refresh"


@pytest.mark.asyncio
class TestEnsureValidToken:
    """Tests for StravaService.ensure_valid_token."""

    async def test_skips_refresh_when_fresh(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
        strava_token_row,
    ) -> None:
        """Does not refresh a token that hasn't expired."""
        strava_token_row.expires_at = datetime.now(timezone.utc) + timedelta(hours=5)
        db_session.add(strava_token_row)
        await db_session.commit()

        service = StravaService(settings, db_session)

        with patch.object(service, "refresh_token") as mock_refresh:
            token = await service.ensure_valid_token(test_user.id)

        mock_refresh.assert_not_called()
        assert token.access_token == "strava-access-token"

    async def test_refreshes_when_expired(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
        strava_token_row,
    ) -> None:
        """Refreshes a token that is past expiry."""
        strava_token_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.add(strava_token_row)
        await db_session.commit()

        service = StravaService(settings, db_session)

        with patch.object(service, "refresh_token", new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = strava_token_row
            await service.ensure_valid_token(test_user.id)

        mock_refresh.assert_called_once()

    async def test_raises_when_not_connected(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
    ) -> None:
        """Raises ValueError when user has no Strava connection."""
        service = StravaService(settings, db_session)

        with pytest.raises(ValueError, match="Strava not connected"):
            await service.ensure_valid_token(test_user.id)


@pytest.mark.asyncio
class TestFetchActivities:
    """Tests for StravaService.fetch_activities."""

    async def test_filters_runs_only(
        self, settings: Settings, db_session: AsyncSession
    ) -> None:
        """Only returns Run/TrailRun/VirtualRun activities."""
        service = StravaService(settings, db_session)
        activities_response = [
            _make_activity(1, sport_type="Run"),
            _make_activity(2, sport_type="Ride"),
            _make_activity(3, sport_type="TrailRun"),
            _make_activity(4, sport_type="Swim"),
            _make_activity(5, sport_type="VirtualRun"),
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = activities_response
        mock_resp.raise_for_status = MagicMock()

        with patch("src.services.strava.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.fetch_activities("token")

        assert len(result) == 3
        assert {a.sport_type for a in result} == {"Run", "TrailRun", "VirtualRun"}

    async def test_handles_empty_response(
        self, settings: Settings, db_session: AsyncSession
    ) -> None:
        """Returns empty list when Strava returns no activities."""
        service = StravaService(settings, db_session)
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch("src.services.strava.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await service.fetch_activities("token")

        assert result == []


@pytest.mark.asyncio
class TestImportActivities:
    """Tests for StravaService.import_activities."""

    async def test_imports_and_converts_units(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
        strava_token_row,
    ) -> None:
        """Imports activities with correct unit conversion (m→km, s→min)."""
        db_session.add(strava_token_row)
        await db_session.commit()

        service = StravaService(settings, db_session)
        activities = [
            StravaActivity(
                id=100,
                name="Morning Run",
                sport_type="Run",
                distance=10000.0,  # 10 km
                moving_time=3600,  # 60 min
                start_date="2026-03-20T08:00:00Z",
                average_heartrate=150.0,
            ),
        ]

        with patch.object(service, "ensure_valid_token", new_callable=AsyncMock) as mock_token:
            mock_token.return_value = strava_token_row
            with patch.object(service, "fetch_activities", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = activities
                imported, total = await service.import_activities(test_user.id)

        assert imported == 1
        assert total == 1

        result = await db_session.execute(
            select(WorkoutLog).where(WorkoutLog.user_id == test_user.id)
        )
        log = result.scalar_one()
        assert log.actual_distance_km == 10.0
        assert log.actual_duration_minutes == 60.0
        assert log.avg_heart_rate == 150
        assert log.source == "strava"
        assert log.strava_activity_id == 100

    async def test_deduplicates(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
        strava_token_row,
    ) -> None:
        """Skips activities that already exist by strava_activity_id."""
        db_session.add(strava_token_row)
        # Pre-existing log
        existing = WorkoutLog(
            user_id=test_user.id,
            source="strava",
            strava_activity_id=100,
            actual_distance_km=5.0,
            actual_duration_minutes=30.0,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(existing)
        await db_session.commit()

        service = StravaService(settings, db_session)
        activities = [
            StravaActivity(
                id=100, name="Dup", sport_type="Run",
                distance=5000, moving_time=1800, start_date="2026-03-20T08:00:00Z",
            ),
            StravaActivity(
                id=101, name="New", sport_type="Run",
                distance=8000, moving_time=2400, start_date="2026-03-21T08:00:00Z",
            ),
        ]

        with patch.object(service, "ensure_valid_token", new_callable=AsyncMock) as mock_token:
            mock_token.return_value = strava_token_row
            with patch.object(service, "fetch_activities", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = activities
                imported, total = await service.import_activities(test_user.id)

        assert imported == 1
        assert total == 2


@pytest.mark.asyncio
class TestEstimateWeeklyMileage:
    """Tests for StravaService.estimate_weekly_mileage."""

    async def test_computes_average(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
    ) -> None:
        """Computes average weekly mileage from recent Strava logs."""
        now = datetime.now(timezone.utc)
        for i in range(4):
            log = WorkoutLog(
                user_id=test_user.id,
                source="strava",
                strava_activity_id=200 + i,
                actual_distance_km=10.0,
                actual_duration_minutes=60.0,
                completed_at=now - timedelta(weeks=i),
            )
            db_session.add(log)
        await db_session.commit()

        service = StravaService(settings, db_session)
        result = await service.estimate_weekly_mileage(test_user.id, weeks=4)

        assert result is not None
        assert result == 10.0  # 40 km / 4 weeks

    async def test_returns_none_for_no_data(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
    ) -> None:
        """Returns None when there are no Strava logs."""
        service = StravaService(settings, db_session)
        result = await service.estimate_weekly_mileage(test_user.id)
        assert result is None


@pytest.mark.asyncio
class TestDisconnect:
    """Tests for StravaService.disconnect."""

    async def test_deletes_token(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
        strava_token_row,
    ) -> None:
        """Disconnect removes the StravaToken row."""
        db_session.add(strava_token_row)
        await db_session.commit()

        service = StravaService(settings, db_session)

        with patch("src.services.strava.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await service.disconnect(test_user.id)

        result = await db_session.execute(
            select(StravaToken).where(StravaToken.user_id == test_user.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_noop_when_not_connected(
        self,
        settings: Settings,
        db_session: AsyncSession,
        test_user,
    ) -> None:
        """Disconnect is a no-op when user has no Strava connection."""
        service = StravaService(settings, db_session)
        await service.disconnect(test_user.id)  # Should not raise
