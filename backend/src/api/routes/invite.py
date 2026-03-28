"""Invite code routes — redeem codes, request access, and admin management.

Users can redeem invite codes directly or request access.
Admin users can create codes, approve/deny requests.
On approval, an invite code is auto-generated and assigned.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.api.rate_limit import limiter
from src.db.models import InviteCode, InviteRequest, User

logger = logging.getLogger(__name__)

DENY_COOLDOWN_DAYS = 30

router = APIRouter(prefix="/invite", tags=["invite"])


class RedeemRequest(BaseModel):
    """Request body for redeeming an invite code.

    Attributes:
        code: The invite code to redeem.
    """

    code: str = Field(..., min_length=1, max_length=20)


class RedeemResponse(BaseModel):
    """Response after successfully redeeming an invite code.

    Attributes:
        redeemed: Whether the code was successfully redeemed.
        code: The redeemed code.
    """

    redeemed: bool
    code: str


class InviteCodeResponse(BaseModel):
    """Response for an invite code.

    Attributes:
        code: The invite code string.
        max_uses: Maximum allowed redemptions.
        use_count: Current number of redemptions.
        expires_at: Optional expiry time.
        created_at: Creation time.
    """

    code: str
    max_uses: int
    use_count: int
    expires_at: datetime | None
    created_at: datetime


class CreateInviteRequest(BaseModel):
    """Request body for creating invite codes.

    Attributes:
        count: Number of codes to generate.
        max_uses: Maximum uses per code.
        prefix: Code prefix.
    """

    count: int = Field(default=1, ge=1, le=50)
    max_uses: int = Field(default=1, ge=1, le=100)
    prefix: str = Field(default="MILE", min_length=1, max_length=10, pattern=r"^[A-Z0-9]+$")


@router.post("/redeem", response_model=RedeemResponse)
@limiter.limit("10/minute")
async def redeem_invite_code(
    request: Request,
    body: RedeemRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RedeemResponse:
    """Redeem an invite code to unlock plan generation.

    Args:
        request: The incoming request.
        body: Request with invite code.
        user: Authenticated user.
        session: Database session.

    Returns:
        RedeemResponse on success.

    Raises:
        HTTPException: 400 if already redeemed, code invalid/expired/maxed.
    """
    if user.invite_code_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already redeemed an invite code.",
        )

    code_str = body.code.strip().upper()

    # Atomic: increment use_count only if under max_uses
    result = await session.execute(
        update(InviteCode)
        .where(
            InviteCode.code == code_str,
            InviteCode.use_count < InviteCode.max_uses,
        )
        .values(use_count=InviteCode.use_count + 1)
        .returning(InviteCode.code)
    )
    updated = result.scalar_one_or_none()

    if updated is None:
        # Check if the code exists at all (for better error message)
        check = await session.execute(select(InviteCode).where(InviteCode.code == code_str))
        existing = check.scalar_one_or_none()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invite code.",
            )
        if existing.expires_at and existing.expires_at < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invite code has expired.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite code has reached its maximum uses.",
        )

    # Check expiry (if set)
    code_row = await session.execute(select(InviteCode).where(InviteCode.code == code_str))
    invite_code = code_row.scalar_one()
    if invite_code.expires_at and invite_code.expires_at < datetime.now(UTC):
        # Roll back the increment
        await session.execute(
            update(InviteCode)
            .where(InviteCode.code == code_str)
            .values(use_count=InviteCode.use_count - 1)
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite code has expired.",
        )

    user.invite_code_used = code_str
    await session.commit()

    return RedeemResponse(redeemed=True, code=code_str)


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------


def _require_admin(user: User) -> None:
    """Raise 403 if user is not an admin.

    Args:
        user: The current user.

    Raises:
        HTTPException: 403 if not admin.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )


@router.post("/admin/codes", response_model=list[InviteCodeResponse])
@limiter.limit("10/minute")
async def create_invite_codes(
    request: Request,
    body: CreateInviteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[InviteCodeResponse]:
    """Create new invite codes (admin only).

    Args:
        request: The incoming request.
        body: Creation options.
        user: Authenticated admin user.
        session: Database session.

    Returns:
        List of created invite codes.
    """
    _require_admin(user)

    codes: list[InviteCode] = []
    for _ in range(body.count):
        suffix = secrets.token_urlsafe(8)[:8]
        code = InviteCode(
            code=f"{body.prefix}-{suffix}",
            max_uses=body.max_uses,
        )
        session.add(code)
        codes.append(code)

    await session.commit()

    return [
        InviteCodeResponse(
            code=c.code,
            max_uses=c.max_uses,
            use_count=c.use_count,
            expires_at=c.expires_at,
            created_at=c.created_at,
        )
        for c in codes
    ]


@router.get("/admin/codes", response_model=list[InviteCodeResponse])
async def list_invite_codes(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[InviteCodeResponse]:
    """List all invite codes (admin only).

    Args:
        user: Authenticated admin user.
        session: Database session.

    Returns:
        List of all invite codes.
    """
    _require_admin(user)

    result = await session.execute(select(InviteCode))
    codes = result.scalars().all()

    return [
        InviteCodeResponse(
            code=c.code,
            max_uses=c.max_uses,
            use_count=c.use_count,
            expires_at=c.expires_at,
            created_at=c.created_at,
        )
        for c in codes
    ]


# ---------------------------------------------------------------------------
# Invite request routes
# ---------------------------------------------------------------------------

# Import schemas used by request endpoints
from src.api.schemas import InviteRequestAdminResponse, InviteRequestResponse, MessageResponse


@router.post("/request", response_model=InviteRequestResponse)
@limiter.limit("5/minute")
async def request_invite(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> InviteRequestResponse:
    """Request an invite code.

    Creates a pending invite request. Returns 409 if a pending request
    already exists. Enforces a 30-day cooldown after denial.

    Args:
        request: The incoming request.
        user: Authenticated user.
        session: Database session.

    Returns:
        InviteRequestResponse with the new request.

    Raises:
        HTTPException: 400 if user already has invite, 409 if pending exists,
            429 if denied within cooldown.
    """
    if user.invite_code_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an invite code.",
        )

    # Check for existing request
    result = await session.execute(
        select(InviteRequest)
        .where(InviteRequest.user_id == user.id)
        .order_by(InviteRequest.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a pending invite request.",
            )
        if existing.status == "denied":
            cooldown_end = existing.updated_at + timedelta(days=DENY_COOLDOWN_DAYS)
            if datetime.now(UTC) < cooldown_end:
                days_left = (cooldown_end - datetime.now(UTC)).days + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Request denied. You can request again in {days_left} days.",
                )

    invite_request = InviteRequest(user_id=user.id, status="pending")
    session.add(invite_request)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending invite request.",
        )
    await session.refresh(invite_request)

    # Fire Discord notification (truly non-blocking via background task)
    async def _notify_discord() -> None:
        try:
            from src.api.notifications import _strip_discord_markdown, send_discord_notification

            safe_name = _strip_discord_markdown(user.name)
            safe_email = _strip_discord_markdown(user.email)
            await send_discord_notification(f"New invite request from {safe_name} ({safe_email})")
        except Exception:
            logger.warning("Failed to send Discord notification", exc_info=True)

    asyncio.create_task(_notify_discord())

    return InviteRequestResponse(
        id=invite_request.id,
        status=invite_request.status,
        created_at=invite_request.created_at,
        updated_at=invite_request.updated_at,
    )


@router.get("/request/status", response_model=InviteRequestResponse | None)
@limiter.limit("30/minute")
async def get_request_status(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> InviteRequestResponse | None:
    """Get the current user's most recent invite request status.

    Args:
        request: The incoming request.
        user: Authenticated user.
        session: Database session.

    Returns:
        InviteRequestResponse or null if no request exists.
    """
    result = await session.execute(
        select(InviteRequest)
        .where(InviteRequest.user_id == user.id)
        .order_by(InviteRequest.created_at.desc())
        .limit(1)
    )
    req = result.scalar_one_or_none()
    if req is None:
        return None
    return InviteRequestResponse(
        id=req.id,
        status=req.status,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


# ---------------------------------------------------------------------------
# Admin request management
# ---------------------------------------------------------------------------


@router.get("/admin/requests", response_model=list[InviteRequestAdminResponse])
@limiter.limit("30/minute")
async def list_invite_requests(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    status_filter: str | None = None,
) -> list[InviteRequestAdminResponse]:
    """List invite requests (admin only).

    Args:
        request: The incoming request.
        user: Authenticated admin user.
        session: Database session.
        status_filter: Optional status filter (pending/approved/denied).

    Returns:
        List of invite requests with user info.
    """
    _require_admin(user)

    valid_statuses = {"pending", "approved", "denied"}
    if status_filter and status_filter not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status_filter. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    query = (
        select(InviteRequest, User)
        .join(User, InviteRequest.user_id == User.id)
        .order_by(InviteRequest.created_at.desc())
    )
    if status_filter:
        query = query.where(InviteRequest.status == status_filter)

    result = await session.execute(query)
    rows = result.all()

    return [
        InviteRequestAdminResponse(
            id=req.id,
            user_id=req.user_id,
            user_email=u.email,
            user_name=u.name,
            status=req.status,
            created_at=req.created_at,
        )
        for req, u in rows
    ]


@router.post("/admin/requests/{request_id}/approve", response_model=MessageResponse)
@limiter.limit("20/minute")
async def approve_invite_request(
    request: Request,
    request_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Approve an invite request (admin only).

    Auto-generates an invite code and assigns it to the requesting user.
    Sends an approval email notification.

    Args:
        request: The incoming request.
        request_id: ID of the invite request to approve.
        user: Authenticated admin user.
        session: Database session.

    Returns:
        Success message with assigned code.

    Raises:
        HTTPException: 403 if not admin, 404 if request not found.
    """
    _require_admin(user)

    from uuid import UUID

    try:
        req_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid request ID.")

    result = await session.execute(select(InviteRequest).where(InviteRequest.id == req_uuid))
    invite_req = result.scalar_one_or_none()
    if invite_req is None:
        raise HTTPException(status_code=404, detail="Invite request not found.")

    if invite_req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already {invite_req.status}.",
        )

    # Generate and assign invite code
    suffix = secrets.token_urlsafe(8)[:8]
    code_str = f"MILE-{suffix}"
    code = InviteCode(code=code_str, max_uses=1, use_count=1)
    session.add(code)

    # Assign to requesting user
    req_user_result = await session.execute(select(User).where(User.id == invite_req.user_id))
    req_user = req_user_result.scalar_one()
    req_user.invite_code_used = code_str

    # Update request status
    invite_req.status = "approved"
    invite_req.updated_at = datetime.now(UTC)

    await session.commit()

    # Send approval email (truly non-blocking via background task)
    async def _notify_email() -> None:
        try:
            from src.api.notifications import send_approval_email

            await send_approval_email(req_user.email, req_user.name)
        except Exception:
            logger.warning("Failed to send approval email", exc_info=True)

    asyncio.create_task(_notify_email())

    return MessageResponse(detail=f"Approved. Code {code_str} assigned to {req_user.email}.")


@router.post("/admin/requests/{request_id}/deny", response_model=MessageResponse)
@limiter.limit("20/minute")
async def deny_invite_request(
    request: Request,
    request_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Deny an invite request (admin only).

    Args:
        request: The incoming request.
        request_id: ID of the invite request to deny.
        user: Authenticated admin user.
        session: Database session.

    Returns:
        Success message.

    Raises:
        HTTPException: 403 if not admin, 404 if request not found.
    """
    _require_admin(user)

    from uuid import UUID

    try:
        req_uuid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid request ID.")

    result = await session.execute(select(InviteRequest).where(InviteRequest.id == req_uuid))
    invite_req = result.scalar_one_or_none()
    if invite_req is None:
        raise HTTPException(status_code=404, detail="Invite request not found.")

    if invite_req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already {invite_req.status}.",
        )

    invite_req.status = "denied"
    invite_req.updated_at = datetime.now(UTC)
    await session.commit()

    return MessageResponse(detail="Request denied.")
