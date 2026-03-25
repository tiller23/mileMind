"""FastAPI application entry point.

Usage:
    uvicorn src.api.main:create_app --factory --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from src.api.rate_limit import limiter, rate_limit_exceeded_handler
from src.config import get_settings

logger = logging.getLogger(__name__)


async def _cleanup_revoked_tokens() -> None:
    """Periodically remove expired entries from the revoked_tokens table."""
    while True:
        await asyncio.sleep(3600)  # Every hour
        try:
            from sqlalchemy import delete

            from src.db.models import RevokedToken
            from src.db.session import get_session

            async for session in get_session():
                now = datetime.now(timezone.utc)
                result = await session.execute(
                    delete(RevokedToken).where(RevokedToken.expires_at < now)
                )
                await session.commit()
                if result.rowcount > 0:
                    logger.info("Cleaned up %d expired revoked tokens", result.rowcount)
                break
        except Exception:
            logger.exception("Error cleaning up revoked tokens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the application.
    """
    # Startup: launch background cleanup task
    cleanup_task = asyncio.create_task(_cleanup_revoked_tokens())
    yield
    # Shutdown: cancel cleanup and dispose engine
    cleanup_task.cancel()
    from src.db.session import _get_engine

    engine = _get_engine()
    if engine is not None:
        await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app with routes and middleware.
    """
    settings = get_settings()

    app = FastAPI(
        title="MileMind API",
        description="AI-powered running training optimizer",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # CORS — use cors_origins if set, otherwise fall back to frontend_url
    origins = settings.cors_origins if settings.cors_origins else [settings.frontend_url]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Register routes
    from src.api.routes.auth import router as auth_router
    from src.api.routes.invite import router as invite_router
    from src.api.routes.jobs import router as jobs_router
    from src.api.routes.plans import router as plans_router
    from src.api.routes.profile import router as profile_router
    from src.api.routes.strava import router as strava_router

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(invite_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(plans_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(strava_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        """Health check endpoint.

        Returns:
            Status dict.
        """
        return {"status": "ok"}

    return app
