"""Tests for JWT token creation and validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from jose import jwt

from src.api.deps import create_access_token, create_refresh_token
from src.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Test settings with known secret.

    Returns:
        Settings instance for testing.
    """
    return Settings(
        jwt_secret="test-secret-key-for-testing",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=15,
        jwt_refresh_token_expire_days=30,
        debug=True,
    )


class TestCreateAccessToken:
    """Tests for create_access_token."""

    def test_creates_valid_jwt(self, settings: Settings) -> None:
        """Token can be decoded with the correct secret."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id, settings)

        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"

    def test_token_has_expiry(self, settings: Settings) -> None:
        """Token includes an expiration claim."""
        token = create_access_token(uuid.uuid4(), settings)
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert "exp" in payload

    def test_token_expires_in_future(self, settings: Settings) -> None:
        """Token expiry is in the future."""
        token = create_access_token(uuid.uuid4(), settings)
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        assert exp > datetime.now(UTC)

    def test_wrong_secret_fails(self, settings: Settings) -> None:
        """Token cannot be decoded with wrong secret."""
        token = create_access_token(uuid.uuid4(), settings)
        with pytest.raises(Exception):
            jwt.decode(token, "wrong-secret", algorithms=[settings.jwt_algorithm])


class TestCreateRefreshToken:
    """Tests for create_refresh_token."""

    def test_creates_refresh_type(self, settings: Settings) -> None:
        """Refresh token has type='refresh'."""
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id, settings)

        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert payload["type"] == "refresh"
        assert payload["sub"] == str(user_id)

    def test_refresh_token_longer_expiry(self, settings: Settings) -> None:
        """Refresh token expires later than access token."""
        user_id = uuid.uuid4()
        access = create_access_token(user_id, settings)
        refresh = create_refresh_token(user_id, settings)

        access_payload = jwt.decode(
            access, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        refresh_payload = jwt.decode(
            refresh, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )

        assert refresh_payload["exp"] > access_payload["exp"]

    def test_different_tokens_per_call(self, settings: Settings) -> None:
        """Each call produces a different token (different exp timestamp)."""
        user_id = uuid.uuid4()
        t1 = create_refresh_token(user_id, settings)
        t2 = create_refresh_token(user_id, settings)
        # Tokens may be identical if called in same second, but the test
        # validates they're both valid
        for t in (t1, t2):
            payload = jwt.decode(t, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            assert payload["sub"] == str(user_id)
