"""Rate limiting configuration using slowapi.

Provides per-endpoint rate limits keyed by user ID (authenticated)
or IP address (unauthenticated).

Usage:
    from src.api.rate_limit import limiter
    @router.post("/endpoint")
    @limiter.limit("10/minute")
    async def endpoint(request: Request): ...
"""

from __future__ import annotations

import logging

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _get_rate_limit_key(request: Request) -> str:
    """Extract rate limit key from request.

    Uses user_id from JWT cookie for authenticated requests,
    falls back to IP address for unauthenticated requests.

    Args:
        request: The incoming request.

    Returns:
        String key for rate limiting.
    """
    # Try to get user ID from access_token cookie (without full JWT decode)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            from jose import jwt as jose_jwt

            from src.config import get_settings

            settings = get_settings()
            payload = jose_jwt.decode(
                access_token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_rate_limit_key, enabled=True)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Handle rate limit exceeded errors.

    Args:
        request: The request that exceeded the limit.
        exc: The rate limit exception.

    Returns:
        JSON 429 response.
    """
    logger.warning(
        "Rate limit exceeded: %s from %s",
        exc.detail,
        get_remote_address(request),
    )
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )
