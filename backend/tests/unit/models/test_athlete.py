"""Tests for AthleteProfile cache_key method and field boundary validation."""

import re

import pytest
from pydantic import ValidationError

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


class TestAthleteProfileBoundary:
    """Pydantic Field boundary tests for AthleteProfile.

    Each test verifies that the model accepts values at valid boundaries and
    raises ValidationError for values that violate Field constraints.  Having
    explicit boundary tests prevents silent regressions when someone widens or
    tightens a constraint in athlete.py.
    """

    # ------------------------------------------------------------------
    # age: ge=10, le=100
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("age", [9, 0, -1])
    def test_age_below_minimum_is_rejected(self, age: int) -> None:
        """age values below 10 must raise ValidationError (ge=10)."""
        with pytest.raises(ValidationError):
            _make_profile(age=age)

    @pytest.mark.parametrize("age", [10, 55, 100])
    def test_age_within_bounds_is_accepted(self, age: int) -> None:
        """age values 10–100 inclusive must be accepted."""
        profile = _make_profile(age=age)
        assert profile.age == age

    def test_age_above_maximum_is_rejected(self) -> None:
        """age=101 must raise ValidationError (le=100)."""
        with pytest.raises(ValidationError):
            _make_profile(age=101)

    # ------------------------------------------------------------------
    # vo2max: ge=15.0, le=90.0, optional
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "vo2max, should_pass",
        [
            (14.9, False),
            (15.0, True),
            (52.5, True),
            (90.0, True),
            (90.1, False),
        ],
    )
    def test_vo2max_boundaries(self, vo2max: float, should_pass: bool) -> None:
        """vo2max must satisfy ge=15.0, le=90.0 when provided."""
        if should_pass:
            profile = _make_profile(vo2max=vo2max)
            assert profile.vo2max == pytest.approx(vo2max)
        else:
            with pytest.raises(ValidationError):
                _make_profile(vo2max=vo2max)

    def test_vo2max_none_is_accepted(self) -> None:
        """vo2max is optional; None must be accepted."""
        profile = _make_profile(vo2max=None)
        assert profile.vo2max is None

    # ------------------------------------------------------------------
    # vdot: ge=15.0, le=85.0, optional
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "vdot, should_pass",
        [
            (14.9, False),
            (15.0, True),
            (50.0, True),
            (85.0, True),
            (85.1, False),
        ],
    )
    def test_vdot_boundaries(self, vdot: float, should_pass: bool) -> None:
        """vdot must satisfy ge=15.0, le=85.0 when provided."""
        if should_pass:
            profile = _make_profile(vdot=vdot)
            assert profile.vdot == pytest.approx(vdot)
        else:
            with pytest.raises(ValidationError):
                _make_profile(vdot=vdot)

    def test_vdot_none_is_accepted(self) -> None:
        """vdot is optional; None must be accepted."""
        profile = _make_profile(vdot=None)
        assert profile.vdot is None

    # ------------------------------------------------------------------
    # weekly_mileage_base: ge=0.0
    # ------------------------------------------------------------------

    def test_weekly_mileage_base_negative_is_rejected(self) -> None:
        """weekly_mileage_base=-0.1 must raise ValidationError (ge=0.0)."""
        with pytest.raises(ValidationError):
            _make_profile(weekly_mileage_base=-0.1)

    def test_weekly_mileage_base_zero_is_accepted(self) -> None:
        """weekly_mileage_base=0.0 must be accepted (brand-new runner)."""
        profile = _make_profile(weekly_mileage_base=0.0)
        assert profile.weekly_mileage_base == pytest.approx(0.0)

    # ------------------------------------------------------------------
    # hr_max: ge=100, le=230, optional
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "hr_max, should_pass",
        [
            (99, False),
            (100, True),
            (185, True),
            (230, True),
            (231, False),
        ],
    )
    def test_hr_max_boundaries(self, hr_max: int, should_pass: bool) -> None:
        """hr_max must satisfy ge=100, le=230 when provided."""
        if should_pass:
            profile = _make_profile(hr_max=hr_max)
            assert profile.hr_max == hr_max
        else:
            with pytest.raises(ValidationError):
                _make_profile(hr_max=hr_max)

    def test_hr_max_none_is_accepted(self) -> None:
        """hr_max is optional; None must be accepted."""
        profile = _make_profile(hr_max=None)
        assert profile.hr_max is None

    # ------------------------------------------------------------------
    # hr_rest: ge=30, le=100, optional
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "hr_rest, should_pass",
        [
            (29, False),
            (30, True),
            (60, True),
            (100, True),
            (101, False),
        ],
    )
    def test_hr_rest_boundaries(self, hr_rest: int, should_pass: bool) -> None:
        """hr_rest must satisfy ge=30, le=100 when provided."""
        if should_pass:
            profile = _make_profile(hr_rest=hr_rest)
            assert profile.hr_rest == hr_rest
        else:
            with pytest.raises(ValidationError):
                _make_profile(hr_rest=hr_rest)

    def test_hr_rest_none_is_accepted(self) -> None:
        """hr_rest is optional; None must be accepted."""
        profile = _make_profile(hr_rest=None)
        assert profile.hr_rest is None

    # ------------------------------------------------------------------
    # name: min_length=1, max_length=100
    # ------------------------------------------------------------------

    def test_name_empty_string_is_rejected(self) -> None:
        """name="" must raise ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            _make_profile(name="")

    def test_name_single_char_is_accepted(self) -> None:
        """name of length 1 is the minimum valid value."""
        profile = _make_profile(name="A")
        assert profile.name == "A"

    def test_name_max_length_is_accepted(self) -> None:
        """name of exactly 100 characters must be accepted."""
        long_name = "A" * 100
        profile = _make_profile(name=long_name)
        assert profile.name == long_name

    def test_name_over_max_length_is_rejected(self) -> None:
        """name of 101 characters must raise ValidationError (max_length=100)."""
        with pytest.raises(ValidationError):
            _make_profile(name="A" * 101)

    # ------------------------------------------------------------------
    # injury_history: max_length=500
    # ------------------------------------------------------------------

    def test_injury_history_at_max_length_is_accepted(self) -> None:
        """injury_history of exactly 500 characters must be accepted."""
        text = "A" * 500
        profile = _make_profile(injury_history=text)
        assert profile.injury_history == text

    def test_injury_history_over_max_length_is_rejected(self) -> None:
        """injury_history of 501 characters must raise ValidationError (max_length=500)."""
        with pytest.raises(ValidationError):
            _make_profile(injury_history="A" * 501)

    # ------------------------------------------------------------------
    # risk_tolerance: enum validation
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("valid_value", ["conservative", "moderate", "aggressive"])
    def test_risk_tolerance_valid_strings_are_accepted(self, valid_value: str) -> None:
        """All three RiskTolerance string values must be accepted."""
        profile = _make_profile(risk_tolerance=valid_value)  # type: ignore[arg-type]
        assert profile.risk_tolerance == RiskTolerance(valid_value)

    @pytest.mark.parametrize("invalid_value", ["reckless", "medium", "low", "", "MODERATE"])
    def test_risk_tolerance_invalid_string_is_rejected(self, invalid_value: str) -> None:
        """Strings outside the RiskTolerance enum must raise ValidationError."""
        with pytest.raises(ValidationError):
            _make_profile(risk_tolerance=invalid_value)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # max_weekly_increase_pct: ge=0.01, le=0.20
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "pct, should_pass",
        [
            (0.009, False),
            (0.01, True),
            (0.10, True),
            (0.20, True),
            (0.201, False),
        ],
    )
    def test_max_weekly_increase_pct_boundaries(self, pct: float, should_pass: bool) -> None:
        """max_weekly_increase_pct must satisfy ge=0.01, le=0.20."""
        if should_pass:
            profile = _make_profile(max_weekly_increase_pct=pct)
            assert profile.max_weekly_increase_pct == pytest.approx(pct)
        else:
            with pytest.raises(ValidationError):
                _make_profile(max_weekly_increase_pct=pct)

    # ------------------------------------------------------------------
    # training_days_per_week: ge=3, le=7
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "days, should_pass",
        [
            (2, False),
            (3, True),
            (5, True),
            (7, True),
            (8, False),
        ],
    )
    def test_training_days_per_week_boundaries(self, days: int, should_pass: bool) -> None:
        """training_days_per_week must satisfy ge=3, le=7."""
        if should_pass:
            profile = _make_profile(training_days_per_week=days)
            assert profile.training_days_per_week == days
        else:
            with pytest.raises(ValidationError):
                _make_profile(training_days_per_week=days)

    # ------------------------------------------------------------------
    # long_run_cap_pct: ge=0.15, le=0.50
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "cap, should_pass",
        [
            (0.14, False),
            (0.15, True),
            (0.30, True),
            (0.50, True),
            (0.51, False),
        ],
    )
    def test_long_run_cap_pct_boundaries(self, cap: float, should_pass: bool) -> None:
        """long_run_cap_pct must satisfy ge=0.15, le=0.50."""
        if should_pass:
            profile = _make_profile(long_run_cap_pct=cap)
            assert profile.long_run_cap_pct == pytest.approx(cap)
        else:
            with pytest.raises(ValidationError):
                _make_profile(long_run_cap_pct=cap)

    # ------------------------------------------------------------------
    # goal_time_minutes: ge=1.0, optional
    # ------------------------------------------------------------------

    def test_goal_time_minutes_below_minimum_is_rejected(self) -> None:
        """goal_time_minutes=0.9 must raise ValidationError (ge=1.0)."""
        with pytest.raises(ValidationError):
            _make_profile(goal_time_minutes=0.9)

    def test_goal_time_minutes_at_minimum_is_accepted(self) -> None:
        """goal_time_minutes=1.0 is the minimum valid finish time."""
        profile = _make_profile(goal_time_minutes=1.0)
        assert profile.goal_time_minutes == pytest.approx(1.0)

    def test_goal_time_minutes_none_is_accepted(self) -> None:
        """goal_time_minutes is optional; None must be accepted."""
        profile = _make_profile(goal_time_minutes=None)
        assert profile.goal_time_minutes is None

    # ------------------------------------------------------------------
    # frozen=True — mutation must raise
    # ------------------------------------------------------------------

    def test_frozen_model_rejects_attribute_assignment(self) -> None:
        """AthleteProfile is frozen; direct attribute assignment must raise."""
        profile = _make_profile()
        with pytest.raises(Exception):
            profile.age = 25  # type: ignore[misc]

    def test_frozen_model_config_is_frozen(self) -> None:
        """AthleteProfile.model_config must declare frozen=True.

        This confirms the intent is enforced at the model-config level, not just
        via runtime luck.  If someone accidentally removes frozen=True the direct
        assignment test above will catch it at runtime, and this test will catch
        it at the config level as an early signal.
        """
        assert AthleteProfile.model_config.get("frozen") is True
