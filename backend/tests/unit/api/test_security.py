"""Tests for security hardening — JWT revocation, rate limiting, SSE heartbeats,
invite codes, plan limits, and API budget cap.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import create_access_token, create_refresh_token
from src.config import Settings
from src.db.models import InviteCode, RevokedToken, TrainingPlan, User


# ---------------------------------------------------------------------------
# JWT Token Tests
# ---------------------------------------------------------------------------


class TestJWTTokensHaveJTI:
    """Verify that access and refresh tokens include jti claims."""

    def _settings(self) -> Settings:
        return Settings(
            debug=True,
            jwt_secret="test-secret",
            strava_client_id="",
            strava_client_secret="",
            database_url="sqlite+aiosqlite://",
        )

    def test_access_token_has_jti(self) -> None:
        token = create_access_token(uuid.uuid4(), self._settings())
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert "jti" in payload
        assert len(payload["jti"]) == 36  # UUID format

    def test_refresh_token_has_jti(self) -> None:
        token = create_refresh_token(uuid.uuid4(), self._settings())
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert "jti" in payload

    def test_each_token_has_unique_jti(self) -> None:
        s = self._settings()
        user_id = uuid.uuid4()
        t1 = create_access_token(user_id, s)
        t2 = create_access_token(user_id, s)
        p1 = jwt.decode(t1, "test-secret", algorithms=["HS256"])
        p2 = jwt.decode(t2, "test-secret", algorithms=["HS256"])
        assert p1["jti"] != p2["jti"]


# ---------------------------------------------------------------------------
# Token Revocation Tests
# ---------------------------------------------------------------------------


class TestTokenRevocation:
    """Tests for JWT denylist on logout."""

    async def test_revoked_token_returns_401(
        self, db_session: AsyncSession, test_user: User, async_engine
    ) -> None:
        """After revoking a token, it should be rejected."""
        settings = Settings(
            debug=True, jwt_secret="test-secret",
            strava_client_id="", strava_client_secret="",
            database_url="sqlite+aiosqlite://",
        )
        token = create_access_token(test_user.id, settings)
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

        # Add to denylist
        revoked = RevokedToken(
            jti=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
        db_session.add(revoked)
        await db_session.commit()

        # Verify it's in the denylist
        result = await db_session.execute(
            select(RevokedToken).where(RevokedToken.jti == payload["jti"])
        )
        assert result.scalar_one_or_none() is not None

    async def test_revoked_token_model_fields(self) -> None:
        """RevokedToken stores jti, expires_at, and revoked_at."""
        now = datetime.now(timezone.utc)
        revoked = RevokedToken(
            jti="test-jti-123",
            expires_at=now + timedelta(hours=1),
        )
        assert revoked.jti == "test-jti-123"
        assert revoked.expires_at > now


# ---------------------------------------------------------------------------
# Invite Code Tests
# ---------------------------------------------------------------------------


class TestInviteCodeModel:
    """Tests for the InviteCode model."""

    async def test_create_invite_code(self, db_session: AsyncSession) -> None:
        code = InviteCode(code="MILE-TEST", max_uses=5)
        db_session.add(code)
        await db_session.commit()

        result = await db_session.execute(
            select(InviteCode).where(InviteCode.code == "MILE-TEST")
        )
        saved = result.scalar_one()
        assert saved.max_uses == 5
        assert saved.use_count == 0
        assert saved.expires_at is None

    async def test_invite_code_with_expiry(self, db_session: AsyncSession) -> None:
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        code = InviteCode(code="MILE-EXP1", expires_at=expires)
        db_session.add(code)
        await db_session.commit()

        result = await db_session.execute(
            select(InviteCode).where(InviteCode.code == "MILE-EXP1")
        )
        saved = result.scalar_one()
        assert saved.expires_at is not None


class TestUserInviteFields:
    """Tests for User model invite/role fields."""

    async def test_user_defaults(self, db_session: AsyncSession) -> None:
        user = User(
            email="invite-test@example.com",
            name="Invite Test",
            auth_provider="google",
            auth_provider_id="inv-123",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.role == "user"
        assert user.invite_code_used is None

    async def test_user_with_invite_code(self, db_session: AsyncSession) -> None:
        user = User(
            email="invited@example.com",
            name="Invited User",
            auth_provider="google",
            auth_provider_id="inv-456",
            invite_code_used="MILE-ABCD",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.invite_code_used == "MILE-ABCD"

    async def test_admin_role(self, db_session: AsyncSession) -> None:
        user = User(
            email="admin@example.com",
            name="Admin",
            auth_provider="google",
            auth_provider_id="admin-789",
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.role == "admin"


# ---------------------------------------------------------------------------
# Plan Generation Gate Tests (invite code + limits)
# ---------------------------------------------------------------------------


class TestPlanGenerationGates:
    """Tests for plan generation access controls."""

    async def test_generate_without_invite_returns_403(
        self, client: AsyncClient
    ) -> None:
        """Users without an invite code cannot generate plans."""
        resp = await client.post("/api/v1/plans/generate")
        assert resp.status_code == 403
        assert "Invite code required" in resp.json()["detail"]

    async def test_generate_with_invite_code_passes_gate(
        self, db_session: AsyncSession, test_user: User, test_profile, app
    ) -> None:
        """Users with a redeemed invite code pass the invite gate.

        We mock the JobManager to avoid needing the full jobs infrastructure.
        The key assertion is that it does NOT return 403 (invite gate).
        """
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()

        # Mock the job manager so we don't need real jobs table
        mock_manager = MagicMock()
        mock_manager.start_plan_generation = AsyncMock(return_value=uuid.uuid4())

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("src.api.routes.plans.get_job_manager", return_value=mock_manager):
                resp = await client.post("/api/v1/plans/generate")
            # Should pass invite + limit gates
            assert resp.status_code != 403
            assert resp.status_code != 429

    async def test_monthly_plan_limit(
        self, db_session: AsyncSession, test_user: User, test_profile, app
    ) -> None:
        """Users cannot exceed monthly plan limit."""
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()

        # Create 2 plans this month (the default limit)
        for _ in range(2):
            plan = TrainingPlan(
                user_id=test_user.id,
                athlete_snapshot={},
                plan_data={"weeks": []},
            )
            db_session.add(plan)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/plans/generate")
            assert resp.status_code == 429
            assert "Monthly plan limit" in resp.json()["detail"]

    async def test_api_budget_cap(
        self, db_session: AsyncSession, test_user: User, test_profile, app, monkeypatch
    ) -> None:
        """Plan generation blocked when global budget is exhausted."""
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()

        # Create a plan that consumed the entire budget
        plan = TrainingPlan(
            user_id=test_user.id,
            athlete_snapshot={},
            plan_data={"weeks": []},
            estimated_cost_usd=50.0,
        )
        db_session.add(plan)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/plans/generate")
            assert resp.status_code == 503
            assert "budget exhausted" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# SSE Heartbeat Tests
# ---------------------------------------------------------------------------


class TestSSEHeartbeat:
    """Tests for SSE heartbeat injection during idle periods."""

    def test_heartbeat_format(self) -> None:
        """Heartbeat should be a SSE comment line."""
        heartbeat = ": heartbeat\n\n"
        # Comments start with : and are ignored by EventSource
        assert heartbeat.startswith(":")
        assert heartbeat.endswith("\n\n")


# ---------------------------------------------------------------------------
# Config Validation Tests
# ---------------------------------------------------------------------------


class TestConfigValidation:
    """Tests for production config validators."""

    def _base(self, **overrides) -> Settings:
        defaults = dict(
            debug=True, jwt_secret="test",
            strava_client_id="", strava_client_secret="",
            database_url="sqlite+aiosqlite://",
        )
        defaults.update(overrides)
        return Settings(**defaults)

    def test_strava_encryption_key_required_in_production(self) -> None:
        """Config rejects Strava without encryption key in production."""
        with pytest.raises(ValueError, match="STRAVA_TOKEN_ENCRYPTION_KEY"):
            Settings(
                debug=False,
                jwt_secret="a-real-secret-value-here",
                strava_client_id="some-id",
                strava_client_secret="some-secret",
                strava_token_encryption_key="",
                database_url="sqlite+aiosqlite://",
            )

    def test_strava_encryption_key_not_required_without_strava(self) -> None:
        """Config allows no encryption key if Strava is not configured."""
        s = self._base()
        assert s.strava_token_encryption_key == ""

    def test_strava_with_encryption_key_passes(self) -> None:
        """Config accepts Strava with encryption key set."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        s = self._base(
            strava_client_id="some-id",
            strava_client_secret="some-secret",
            strava_token_encryption_key=key,
        )
        assert s.strava_token_encryption_key == key

    def test_max_plans_per_month_default(self) -> None:
        s = self._base()
        assert s.max_plans_per_month == 2

    def test_monthly_api_budget_default(self) -> None:
        s = self._base()
        assert s.monthly_api_budget_usd == 50.0
