"""FastAPI dependency injection — database session and auth.

Usage:
    @router.get("/protected")
    async def protected(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ):
        ...
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.db.models import RevokedToken, User
from src.db.session import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Yields:
        AsyncSession for database operations.
    """
    async for session in get_session():
        yield session


def create_access_token(
    user_id: UUID,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: User ID to encode in the token.
        settings: App settings (uses get_settings() if None).

    Returns:
        Encoded JWT string.
    """
    if settings is None:
        settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    jti = str(uuid_mod.uuid4())
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
        "jti": jti,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: UUID,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT refresh token.

    Args:
        user_id: User ID to encode in the token.
        settings: App settings (uses get_settings() if None).

    Returns:
        Encoded JWT string.
    """
    if settings is None:
        settings = get_settings()
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    jti = str(uuid_mod.uuid4())
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": jti,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    access_token: Annotated[str | None, Cookie()] = None,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Extract and validate the current user from JWT cookie.

    Args:
        access_token: JWT from httpOnly cookie.
        session: Database session.
        settings: App settings.

    Returns:
        Authenticated User ORM instance.

    Raises:
        HTTPException: 401 if token is missing, invalid, or user not found.
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(
            access_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id_str is None or token_type != "access":
            logger.warning("Auth failed: invalid token claims (type=%s)", token_type)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        user_id = UUID(user_id_str)

        # Require jti claim (all tokens from Phase 5e+ have it)
        jti = payload.get("jti")
        if not jti:
            logger.warning("Auth failed: missing jti for user %s", user_id_str)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token (missing jti)",
            )

        # Check JWT denylist (revoked on logout)
        revoked = await session.execute(select(RevokedToken).where(RevokedToken.jti == jti))
        if revoked.scalar_one_or_none() is not None:
            logger.warning("Auth failed: revoked token jti=%s user=%s", jti, user_id_str)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
    except JWTError:
        logger.warning("Auth failed: JWT decode error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.warning("Auth failed: user not found for id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
