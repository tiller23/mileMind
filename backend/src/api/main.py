"""FastAPI application entry point.

Usage:
    uvicorn src.api.main:create_app --factory --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the application.
    """
    # Startup: nothing needed yet (engine is lazy)
    yield
    # Shutdown: dispose engine
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

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Register routes
    from src.api.routes.auth import router as auth_router
    from src.api.routes.jobs import router as jobs_router
    from src.api.routes.plans import router as plans_router
    from src.api.routes.profile import router as profile_router
    from src.api.routes.strava import router as strava_router

    app.include_router(auth_router, prefix="/api/v1")
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
