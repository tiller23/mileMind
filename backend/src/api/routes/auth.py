"""Authentication routes — Google and Apple OAuth.

Handles OAuth redirect, callback, token issuance, refresh, and logout.
JWT access tokens are stored in httpOnly cookies for security.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_db,
)
from src.api.schemas import OAuthCallbackRequest, TokenResponse, UserResponse
from src.config import Settings, get_settings
from src.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, user: User, settings: Settings) -> TokenResponse:
    """Set access and refresh token cookies on the response.

    Args:
        response: FastAPI response to set cookies on.
        user: Authenticated user.
        settings: App settings for JWT config.

    Returns:
        TokenResponse with the access token.
    """
    access_token = create_access_token(user.id, settings)
    refresh_token = create_refresh_token(user.id, settings)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
    )
    return TokenResponse(access_token=access_token)


async def _find_or_create_user(
    session: AsyncSession,
    email: str,
    name: str,
    auth_provider: str,
    auth_provider_id: str,
    avatar_url: str | None = None,
) -> User:
    """Find existing user by provider ID or create a new one.

    Args:
        session: Database session.
        email: User email.
        name: Display name.
        auth_provider: OAuth provider name.
        auth_provider_id: Provider's user ID.
        avatar_url: Profile picture URL.

    Returns:
        User ORM instance (existing or newly created).
    """
    result = await session.execute(
        select(User).where(
            User.auth_provider == auth_provider,
            User.auth_provider_id == auth_provider_id,
        )
    )
    user = result.scalar_one_or_none()

    if user is not None:
        # Update email/name/avatar if changed
        user.email = email
        user.name = name
        if avatar_url:
            user.avatar_url = avatar_url
        await session.commit()
        await session.refresh(user)
        return user

    # Check if email exists with different provider
    result = await session.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered with another provider",
        )

    user = User(
        email=email,
        name=name,
        auth_provider=auth_provider,
        auth_provider_id=auth_provider_id,
        avatar_url=avatar_url,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/google")
async def google_login(settings: Settings = Depends(get_settings)) -> dict:
    """Return the Google OAuth authorization URL.

    Args:
        settings: App settings with Google client ID.

    Returns:
        Dict with authorization URL for frontend to redirect to.
    """
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )
    redirect_uri = f"{settings.frontend_url}/auth/callback?provider=google"
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.google_client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
    )
    return {"auth_url": auth_url}


@router.post("/google/callback")
async def google_callback(
    data: OAuthCallbackRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Exchange Google authorization code for JWT tokens.

    Args:
        data: Request body with authorization code.
        response: Response for setting cookies.
        session: Database session.
        settings: App settings.

    Returns:
        TokenResponse with access token.

    Raises:
        HTTPException: 400 if code exchange fails.
    """
    code = data.code

    # Exchange code for Google tokens
    import httpx

    redirect_uri = f"{settings.frontend_url}/auth/callback?provider=google"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error("Google token exchange failed: %s", token_resp.text)
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

        tokens = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")

        userinfo = userinfo_resp.json()

    if not userinfo.get("verified_email", False):
        raise HTTPException(
            status_code=400,
            detail="Email not verified with Google",
        )

    user = await _find_or_create_user(
        session=session,
        email=userinfo["email"],
        name=userinfo.get("name", userinfo["email"]),
        auth_provider="google",
        auth_provider_id=userinfo["id"],
        avatar_url=userinfo.get("picture"),
    )

    return _set_auth_cookies(response, user, settings)


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Refresh an access token using the refresh token cookie.

    Args:
        request: Request with refresh_token cookie.
        response: Response for setting new cookies.
        session: Database session.
        settings: App settings.

    Returns:
        TokenResponse with new access token.

    Raises:
        HTTPException: 401 if refresh token is invalid or expired.
    """
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        from uuid import UUID
        user_id = UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return _set_auth_cookies(response, user, settings)


@router.post("/logout")
async def logout(
    response: Response,
    _user: User = Depends(get_current_user),
) -> dict:
    """Clear authentication cookies.

    Args:
        response: Response for clearing cookies.
        _user: Current authenticated user (validates token before logout).

    Returns:
        Success message.
    """
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"detail": "Logged out"}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    """Get the current authenticated user's info.

    Args:
        user: Current authenticated user.

    Returns:
        UserResponse with public user info.
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
    )
