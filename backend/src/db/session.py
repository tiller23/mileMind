"""Async database engine and session factory.

Usage:
    from src.db.session import get_session

    async for session in get_session():
        result = await session.execute(...)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings

_engine = None
_session_factory = None


def _get_engine():
    """Get or create the async engine (lazy singleton).

    Returns:
        AsyncEngine instance.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    """Get or create the session factory (lazy singleton).

    Returns:
        async_sessionmaker bound to the engine.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closing on exit.

    Yields:
        AsyncSession for database operations.
    """
    factory = _get_session_factory()
    async with factory() as session:
        yield session


def reset_engine() -> None:
    """Reset engine and session factory. Used in tests to swap databases.

    Calling this clears the lazy singletons so the next call to
    get_session() creates a fresh engine from current settings.
    """
    global _engine, _session_factory
    _engine = None
    _session_factory = None


def set_engine(engine: "AsyncEngine") -> None:
    """Override the engine directly. Used in tests with SQLite.

    Args:
        engine: An AsyncEngine to use instead of creating from settings.
    """
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
