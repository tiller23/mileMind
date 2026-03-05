"""Tests for AthleteProfile cache_key method."""

import re

from src.models.athlete import AthleteProfile, RiskTolerance


def _make_profile(**overrides: object) -> AthleteProfile:
    """Create a default AthleteProfile with optional overrides."""
    defaults = {
        "name": "Test Runner",
        "age": 30,
        "weekly_mileage_base": 40.0,
        "goal_distance": "10K",
        "risk_tolerance": RiskTolerance.MODERATE,
    }
    defaults.update(overrides)
    return AthleteProfile(**defaults)  # type: ignore[arg-type]


class TestCacheKey:
    """Tests for AthleteProfile.cache_key()."""

    def test_deterministic(self) -> None:
        """Same profile produces same hash every time."""
        profile = _make_profile()
        assert profile.cache_key() == profile.cache_key()

    def test_changes_on_field_change(self) -> None:
        """Different field values produce different hashes."""
        profile_a = _make_profile(age=30)
        profile_b = _make_profile(age=31)
        assert profile_a.cache_key() != profile_b.cache_key()

    def test_sha256_format(self) -> None:
        """Hash is a 64-character lowercase hex string (SHA-256)."""
        key = _make_profile().cache_key()
        assert len(key) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", key)

    def test_with_salt(self) -> None:
        """Salt changes the hash."""
        profile = _make_profile()
        key_unsalted = profile.cache_key()
        key_salted = profile.cache_key(salt="sonnet:opus:full")
        assert key_unsalted != key_salted

    def test_optional_fields_affect_hash(self) -> None:
        """Providing an optional field produces a different hash than omitting it."""
        profile_without = _make_profile()
        profile_with = _make_profile(vo2max=50.0)
        assert profile_without.cache_key() != profile_with.cache_key()

    def test_injury_history_affects_hash(self) -> None:
        """Even small text changes produce different hashes."""
        profile_a = _make_profile(injury_history="None")
        profile_b = _make_profile(injury_history="Knee pain 2024")
        assert profile_a.cache_key() != profile_b.cache_key()

    def test_same_salt_same_profile_is_deterministic(self) -> None:
        """salt + profile → deterministic result."""
        profile = _make_profile()
        salt = "model-a:model-b:full"
        assert profile.cache_key(salt=salt) == profile.cache_key(salt=salt)
