"""Shared test fixtures for API route tests."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Set environment variables for test Settings.

    This must run before any Settings() instantiation to avoid the
    production JWT secret validator.
    """
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-unit-tests")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")

    # Clear the lru_cache so each test gets fresh settings
    from src.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def app(async_engine, db_session: AsyncSession, test_user: User):
    """Create a test FastAPI app with overridden dependencies.

    Args:
        async_engine: Test async engine.
        db_session: Test database session.
        test_user: Pre-created test user.

    Yields:
        Configured FastAPI application.
    """
    from src.api.deps import get_current_user, get_db
    from src.api.main import create_app
    from src.config import get_settings

    app = create_app()

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Async HTTP client for the test app.

    Args:
        app: Test FastAPI app.

    Yields:
        AsyncClient for making requests.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
