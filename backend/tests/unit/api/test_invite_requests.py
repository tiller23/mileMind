"""Tests for invite request flow — request, approve, deny, cooldown."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import InviteCode, InviteRequest, User

pytestmark = pytest.mark.asyncio


class TestRequestInvite:
    """Tests for POST /api/v1/invite/request."""

    async def test_request_invite_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Successfully create an invite request."""
        with patch("src.api.notifications.send_discord_notification", new_callable=AsyncMock):
            resp = await client.post("/api/v1/invite/request")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "id" in data

    async def test_request_invite_duplicate_409(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Duplicate pending request returns 409."""
        req = InviteRequest(user_id=test_user.id, status="pending")
        db_session.add(req)
        await db_session.commit()

        resp = await client.post("/api/v1/invite/request")
        assert resp.status_code == 409
        assert "pending" in resp.json()["detail"]

    async def test_request_invite_already_has_code_400(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """User with existing invite code gets 400."""
        test_user.invite_code_used = "MILE-AAAA"
        await db_session.commit()

        resp = await client.post("/api/v1/invite/request")
        assert resp.status_code == 400
        assert "already have" in resp.json()["detail"]

    async def test_request_invite_denied_cooldown_429(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Denied user within 30-day cooldown gets 429."""
        req = InviteRequest(
            user_id=test_user.id,
            status="denied",
            updated_at=datetime.now(UTC) - timedelta(days=5),
        )
        db_session.add(req)
        await db_session.commit()

        resp = await client.post("/api/v1/invite/request")
        assert resp.status_code == 429
        assert "days" in resp.json()["detail"]

    async def test_request_invite_after_cooldown_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Denied user after 30-day cooldown can request again."""
        req = InviteRequest(
            user_id=test_user.id,
            status="denied",
            updated_at=datetime.now(UTC) - timedelta(days=31),
        )
        db_session.add(req)
        await db_session.commit()

        with patch("src.api.notifications.send_discord_notification", new_callable=AsyncMock):
            resp = await client.post("/api/v1/invite/request")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_request_invite_after_approval_can_request_if_no_code(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Previously approved user (edge case: code cleared) can re-request."""
        req = InviteRequest(user_id=test_user.id, status="approved")
        db_session.add(req)
        await db_session.commit()

        with patch("src.api.notifications.send_discord_notification", new_callable=AsyncMock):
            resp = await client.post("/api/v1/invite/request")
        assert resp.status_code == 200


class TestGetRequestStatus:
    """Tests for GET /api/v1/invite/request/status."""

    async def test_no_request_returns_null(self, client: AsyncClient) -> None:
        """No request returns null."""
        resp = await client.get("/api/v1/invite/request/status")
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_pending_request_status(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """Returns pending request status."""
        req = InviteRequest(user_id=test_user.id, status="pending")
        db_session.add(req)
        await db_session.commit()

        resp = await client.get("/api/v1/invite/request/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"


class TestAdminInviteRequests:
    """Tests for admin request management."""

    async def test_list_requests_requires_admin(self, client: AsyncClient) -> None:
        """Non-admin gets 403."""
        resp = await client.get("/api/v1/invite/admin/requests")
        assert resp.status_code == 403

    async def test_approve_requires_admin(self, client: AsyncClient) -> None:
        """Non-admin gets 403."""
        fake_id = str(uuid.uuid4())
        resp = await client.post(f"/api/v1/invite/admin/requests/{fake_id}/approve")
        assert resp.status_code == 403

    async def test_deny_requires_admin(self, client: AsyncClient) -> None:
        """Non-admin gets 403."""
        fake_id = str(uuid.uuid4())
        resp = await client.post(f"/api/v1/invite/admin/requests/{fake_id}/deny")
        assert resp.status_code == 403

    async def test_admin_can_list_requests(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Admin can list pending requests."""
        test_user.role = "admin"
        req = InviteRequest(user_id=test_user.id, status="pending")
        db_session.add(req)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/invite/admin/requests")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["user_email"] == test_user.email

    async def test_admin_approve_auto_assigns_code(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Approving a request auto-generates and assigns an invite code."""
        test_user.role = "admin"
        req = InviteRequest(user_id=test_user.id, status="pending")
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("src.api.notifications.send_approval_email", new_callable=AsyncMock):
                resp = await client.post(f"/api/v1/invite/admin/requests/{req.id}/approve")
        assert resp.status_code == 200
        assert "Approved" in resp.json()["detail"]

        # Verify user got the code
        await db_session.refresh(test_user)
        assert test_user.invite_code_used is not None
        assert test_user.invite_code_used.startswith("MILE-")

        # Verify request status updated
        await db_session.refresh(req)
        assert req.status == "approved"

        # Verify invite code exists in DB
        code_result = await db_session.execute(
            select(InviteCode).where(InviteCode.code == test_user.invite_code_used)
        )
        code = code_result.scalar_one()
        assert code.use_count == 1

    async def test_admin_deny_sets_status(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Denying a request sets status to denied."""
        test_user.role = "admin"
        req = InviteRequest(user_id=test_user.id, status="pending")
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/v1/invite/admin/requests/{req.id}/deny")
        assert resp.status_code == 200
        assert "denied" in resp.json()["detail"]

        await db_session.refresh(req)
        assert req.status == "denied"

    async def test_approve_already_approved_400(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Approving an already-approved request returns 400."""
        test_user.role = "admin"
        req = InviteRequest(user_id=test_user.id, status="approved")
        db_session.add(req)
        await db_session.commit()
        await db_session.refresh(req)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/v1/invite/admin/requests/{req.id}/approve")
        assert resp.status_code == 400

    async def test_approve_not_found_404(
        self, db_session: AsyncSession, test_user: User, app
    ) -> None:
        """Approving nonexistent request returns 404."""
        test_user.role = "admin"
        await db_session.commit()

        fake_id = str(uuid.uuid4())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/v1/invite/admin/requests/{fake_id}/approve")
        assert resp.status_code == 404


class TestAuthMeInviteFields:
    """Tests for has_invite and invite_request_status on /auth/me."""

    async def test_me_no_invite_no_request(self, client: AsyncClient) -> None:
        """/auth/me returns has_invite=false, invite_request_status=null by default."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_invite"] is False
        assert data["invite_request_status"] is None

    async def test_me_with_invite(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """/auth/me returns has_invite=true when code is redeemed."""
        test_user.invite_code_used = "MILE-TEST"
        await db_session.commit()

        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_invite"] is True

    async def test_me_with_pending_request(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        """/auth/me returns invite_request_status=pending."""
        req = InviteRequest(user_id=test_user.id, status="pending")
        db_session.add(req)
        await db_session.commit()

        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_invite"] is False
        assert data["invite_request_status"] == "pending"
