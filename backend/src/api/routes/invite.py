"""Invite code routes — redeem codes and admin management.

Users redeem invite codes to unlock plan generation.
Admin users can create and list invite codes.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.api.rate_limit import limiter
from src.db.models import InviteCode, User

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
    prefix: str = Field(default="MILE")


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
        check = await session.execute(
            select(InviteCode).where(InviteCode.code == code_str)
        )
        existing = check.scalar_one_or_none()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invite code.",
            )
        if existing.expires_at and existing.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invite code has expired.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite code has reached its maximum uses.",
        )

    # Check expiry (if set)
    code_row = await session.execute(
        select(InviteCode).where(InviteCode.code == code_str)
    )
    invite_code = code_row.scalar_one()
    if invite_code.expires_at and invite_code.expires_at < datetime.now(timezone.utc):
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
        suffix = secrets.token_hex(3).upper()[:4]
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
