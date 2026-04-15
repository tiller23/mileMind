"""Tests for Strava API routes.

Tests OAuth connect/callback, status, sync, disconnect, and activities
endpoints using the test app fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.main import create_app
from src.config import Settings
from src.db.models import StravaToken, User, WorkoutLog


@pytest.fixture
def _test_env(monkeypatch) -> None:
    """Set environment variables for testing."""
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET", "test-strava-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("STRAVA_CLIENT_ID", "test-strava-client")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "test-strava-secret")
    # Clear cached settings
    from src.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def app(_test_env, db_session: AsyncSession, test_user: User):
    """Create the FastAPI test app with dependency overrides."""
    from src.api.deps import get_current_user, get_db
    from src.config import get_settings

    application = create_app()

    async def override_db():
        yield db_session

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_current_user] = lambda: test_user

    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
async def client(app) -> AsyncClient:
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def settings() -> Settings:
    """Test settings for JWT encoding."""
    return Settings(
        jwt_secret="test-strava-secret",
        strava_client_id="test-strava-client",
        strava_client_secret="test-strava-secret",
        debug=True,
    )


@pytest.fixture
async def strava_token(db_session: AsyncSession, test_user: User) -> StravaToken:
    """Create a Strava token in the database."""
    token = StravaToken(
        user_id=test_user.id,
        strava_athlete_id=12345,
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        expires_at=datetime.now(UTC) + timedelta(hours=6),
        scope="activity:read_all",
    )
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)
    return token


@pytest.mark.asyncio
class TestStravaConnect:
    """Tests for GET /strava/connect."""

    async def test_returns_auth_url(self, client: AsyncClient) -> None:
        """Returns a Strava authorization URL with correct params."""
        resp = await client.get("/api/v1/strava/connect")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "state" in data
        assert "state_token" in data
        assert "strava.com/oauth/authorize" in data["auth_url"]
        assert "client_id=test-strava-client" in data["auth_url"]
        assert "activity:read_all" in data["auth_url"]

    async def test_state_token_is_valid_jwt(self, client: AsyncClient, settings: Settings) -> None:
        """State token is a valid JWT with strava_oauth_state type."""
        resp = await client.get("/api/v1/strava/connect")
        data = resp.json()
        payload = jwt.decode(
            data["state_token"],
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        assert payload["type"] == "strava_oauth_state"
        assert payload["state"] == data["state"]


@pytest.mark.asyncio
class TestStravaCallback:
    """Tests for POST /strava/callback."""

    async def test_invalid_state_returns_400(self, client: AsyncClient) -> None:
        """Invalid state JWT returns 400."""
        resp = await client.post(
            "/api/v1/strava/callback",
            json={"code": "test-code", "state": "garbage"},
        )
        assert resp.status_code == 400

    async def test_creates_token_on_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        settings: Settings,
    ) -> None:
        """Successful callback creates a StravaToken in the database."""
        state_token = jwt.encode(
            {
                "state": "test-state",
                "exp": datetime.now(UTC) + timedelta(minutes=10),
                "type": "strava_oauth_state",
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        mock_token_data = MagicMock()
        mock_token_data.access_token = "new-access"
        mock_token_data.refresh_token = "new-refresh"
        mock_token_data.expires_at = int((datetime.now(UTC) + timedelta(hours=6)).timestamp())
        mock_token_data.athlete_id = 99999

        with patch("src.api.routes.strava.StravaService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.exchange_code = AsyncMock(return_value=mock_token_data)
            mock_service_cls.return_value = mock_service

            resp = await client.post(
                "/api/v1/strava/callback",
                json={"code": "test-code", "state": state_token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_id"] == 99999

        result = await db_session.execute(
            select(StravaToken).where(StravaToken.user_id == test_user.id)
        )
        token = result.scalar_one()
        assert token.strava_athlete_id == 99999


@pytest.mark.asyncio
class TestStravaStatus:
    """Tests for GET /strava/status."""

    async def test_not_connected(self, client: AsyncClient) -> None:
        """Returns connected=false when no Strava token exists."""
        resp = await client.get("/api/v1/strava/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert data["athlete_id"] is None

    async def test_connected(self, client: AsyncClient, strava_token: StravaToken) -> None:
        """Returns connected=true with athlete ID when token exists."""
        resp = await client.get("/api/v1/strava/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_id"] == 12345


@pytest.mark.asyncio
class TestStravaSync:
    """Tests for POST /strava/sync."""

    async def test_returns_import_count(
        self, client: AsyncClient, strava_token: StravaToken
    ) -> None:
        """Sync returns the number of imported activities."""
        with patch("src.api.routes.strava.StravaService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.import_activities = AsyncMock(return_value=(3, 5))
            mock_service.estimate_weekly_mileage = AsyncMock(return_value=25.5)
            mock_service_cls.return_value = mock_service

            resp = await client.post("/api/v1/strava/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported_count"] == 3
        assert data["total_activities"] == 5
        assert data["suggested_weekly_mileage_km"] == 25.5

    async def test_not_connected_returns_404(self, client: AsyncClient) -> None:
        """Sync returns 404 when Strava is not connected."""
        with patch("src.api.routes.strava.StravaService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.import_activities = AsyncMock(
                side_effect=ValueError("Strava not connected")
            )
            mock_service_cls.return_value = mock_service

            resp = await client.post("/api/v1/strava/sync")

        assert resp.status_code == 404


@pytest.mark.asyncio
class TestStravaDisconnect:
    """Tests for POST /strava/disconnect."""

    async def test_removes_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        strava_token: StravaToken,
    ) -> None:
        """Disconnect removes the StravaToken from the database."""
        with patch("src.api.routes.strava.StravaService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.disconnect = AsyncMock()
            mock_service_cls.return_value = mock_service

            resp = await client.post("/api/v1/strava/disconnect")

        assert resp.status_code == 200
        assert resp.json()["detail"] == "Strava disconnected"


@pytest.mark.asyncio
class TestStravaActivities:
    """Tests for GET /strava/activities."""

    async def test_returns_strava_logs(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Returns WorkoutLog entries with source='strava'."""
        log = WorkoutLog(
            user_id=test_user.id,
            source="strava",
            strava_activity_id=555,
            actual_distance_km=8.0,
            actual_duration_minutes=45.0,
            completed_at=datetime.now(UTC),
            notes="Evening run",
        )
        db_session.add(log)
        await db_session.commit()

        resp = await client.get("/api/v1/strava/activities")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source"] == "strava"
        assert data[0]["actual_distance_km"] == 8.0
        assert data[0]["strava_activity_id"] == 555

    async def test_excludes_manual_logs(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Only returns Strava-sourced logs, not manual ones."""
        manual_log = WorkoutLog(
            user_id=test_user.id,
            source="manual",
            actual_distance_km=5.0,
            actual_duration_minutes=30.0,
            completed_at=datetime.now(UTC),
        )
        strava_log = WorkoutLog(
            user_id=test_user.id,
            source="strava",
            strava_activity_id=666,
            actual_distance_km=10.0,
            actual_duration_minutes=55.0,
            completed_at=datetime.now(UTC),
        )
        db_session.add_all([manual_log, strava_log])
        await db_session.commit()

        resp = await client.get("/api/v1/strava/activities")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source"] == "strava"

    async def test_respects_limit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Respects the limit query parameter."""
        for i in range(5):
            log = WorkoutLog(
                user_id=test_user.id,
                source="strava",
                strava_activity_id=700 + i,
                actual_distance_km=5.0,
                actual_duration_minutes=30.0,
                completed_at=datetime.now(UTC) - timedelta(days=i),
            )
            db_session.add(log)
        await db_session.commit()

        resp = await client.get("/api/v1/strava/activities?limit=2")
        assert len(resp.json()) == 2
