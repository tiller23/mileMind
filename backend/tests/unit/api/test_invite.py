"""Tests for invite code redemption and admin routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import InviteCode, User


pytestmark = pytest.mark.asyncio


class TestRedeemInviteCode:
    """Tests for POST /api/v1/invite/redeem."""

    async def test_redeem_valid_code(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Successfully redeem a valid invite code."""
        code = InviteCode(code="MILE-AAAA", max_uses=5)
        db_session.add(code)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/invite/redeem", json={"code": "MILE-AAAA"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["redeemed"] is True
        assert data["code"] == "MILE-AAAA"

        # Verify user and code are updated
        await db_session.refresh(test_user)
        assert test_user.invite_code_used == "MILE-AAAA"

        result = await db_session.execute(
            select(InviteCode).where(InviteCode.code == "MILE-AAAA")
        )
        saved = result.scalar_one()
        assert saved.use_count == 1

    async def test_redeem_case_insensitive(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Codes are normalized to uppercase."""
        code = InviteCode(code="MILE-BBBB", max_uses=1)
        db_session.add(code)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/invite/redeem", json={"code": "mile-bbbb"}
        )
        assert resp.status_code == 200

    async def test_redeem_invalid_code_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Invalid code returns 404."""
        resp = await client.post(
            "/api/v1/invite/redeem", json={"code": "FAKE-CODE"}
        )
        assert resp.status_code == 404
        assert "Invalid invite code" in resp.json()["detail"]

    async def test_redeem_maxed_code_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Code at max uses returns 400."""
        code = InviteCode(code="MILE-FULL", max_uses=1, use_count=1)
        db_session.add(code)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/invite/redeem", json={"code": "MILE-FULL"}
        )
        assert resp.status_code == 400
        assert "maximum uses" in resp.json()["detail"]

    async def test_already_redeemed_returns_400(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """User who already has a code gets 400."""
        test_user.invite_code_used = "MILE-PREV"
        await db_session.commit()

        resp = await client.post(
            "/api/v1/invite/redeem", json={"code": "MILE-NEW1"}
        )
        assert resp.status_code == 400
        assert "already redeemed" in resp.json()["detail"]


class TestAdminInviteCodes:
    """Tests for admin invite code management."""

    async def test_create_codes_requires_admin(
        self, client: AsyncClient
    ) -> None:
        """Non-admin users get 403."""
        resp = await client.post(
            "/api/v1/invite/admin/codes",
            json={"count": 1},
        )
        assert resp.status_code == 403
        assert "Admin access required" in resp.json()["detail"]

    async def test_list_codes_requires_admin(
        self, client: AsyncClient
    ) -> None:
        """Non-admin users get 403."""
        resp = await client.get("/api/v1/invite/admin/codes")
        assert resp.status_code == 403

    async def test_admin_can_create_codes(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Admin users can create invite codes."""
        test_user.role = "admin"
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/invite/admin/codes",
                json={"count": 3, "max_uses": 5, "prefix": "TEST"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        for code in data:
            assert code["code"].startswith("TEST-")
            assert code["max_uses"] == 5
            assert code["use_count"] == 0

    async def test_admin_can_list_codes(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Admin users can list all codes."""
        test_user.role = "admin"
        code = InviteCode(code="MILE-LIST", max_uses=1)
        db_session.add(code)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/invite/admin/codes")
        assert resp.status_code == 200
        codes = resp.json()
        assert any(c["code"] == "MILE-LIST" for c in codes)
