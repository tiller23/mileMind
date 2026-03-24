"""Application configuration via pydantic-settings.

Reads from environment variables with sensible defaults for local development.
All secrets must be set via environment (never hardcoded).

Usage:
    from src.config import get_settings
    settings = get_settings()
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        database_url: Async PostgreSQL connection string.
        database_url_sync: Sync connection string for Alembic migrations.
        jwt_secret: Secret key for signing JWT tokens.
        jwt_algorithm: JWT signing algorithm.
        jwt_access_token_expire_minutes: Access token TTL.
        jwt_refresh_token_expire_days: Refresh token TTL.
        google_client_id: Google OAuth client ID.
        google_client_secret: Google OAuth client secret.
        apple_client_id: Apple Sign-In service ID.
        apple_team_id: Apple developer team ID.
        apple_key_id: Apple Sign-In key ID.
        apple_private_key: Apple Sign-In private key (PEM).
        frontend_url: Frontend URL for CORS and OAuth redirects.
        anthropic_api_key: Anthropic API key for Claude.
        strava_client_id: Strava API client ID.
        strava_client_secret: Strava API client secret.
        debug: Enable debug mode.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/milemind"
    database_url_sync: str = "postgresql://localhost:5432/milemind"

    # JWT
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Apple Sign-In
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Anthropic
    anthropic_api_key: str = ""

    # Strava
    strava_client_id: str = ""
    strava_client_secret: str = ""

    # Debug
    debug: bool = False

    @model_validator(mode="after")
    def _check_jwt_secret_in_production(self) -> "Settings":
        """Refuse to start with the default JWT secret in production.

        Returns:
            Self if validation passes.

        Raises:
            ValueError: If jwt_secret is the default and debug is False.
        """
        if not self.debug and self.jwt_secret == "CHANGE-ME-IN-PRODUCTION":
            raise ValueError(
                "jwt_secret must be set to a secure value in production. "
                "Set the JWT_SECRET environment variable."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Returns:
        Settings instance loaded from environment.
    """
    return Settings()
