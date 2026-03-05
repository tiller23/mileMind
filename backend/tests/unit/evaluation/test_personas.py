"""Tests for the evaluation persona definitions.

Validates that all 5 synthetic athlete personas are correctly defined,
produce valid AthleteProfile instances, and have complete expected
behavior specifications.
"""

import pytest

from src.evaluation.personas import (
    ALL_PERSONAS,
    ADVANCED_MARATHONER,
    AGGRESSIVE_SPIKER,
    BEGINNER_RUNNER,
    INJURY_PRONE_RUNNER,
    OVERTRAINED_ATHLETE,
    EvaluationPersona,
    ExpectedBehavior,
    get_persona,
    list_persona_ids,
)
from src.models.athlete import AthleteProfile, RiskTolerance


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


class TestPersonaRegistry:
    """Tests for the persona registry and lookup functions."""

    def test_all_personas_has_five_entries(self) -> None:
        """PRD Section 8.1 specifies exactly 5 synthetic athletes."""
        assert len(ALL_PERSONAS) == 5

    def test_all_persona_ids_are_unique(self) -> None:
        """No duplicate persona IDs."""
        ids = [p.persona_id for p in ALL_PERSONAS]
        assert len(ids) == len(set(ids))

    def test_list_persona_ids_returns_sorted(self) -> None:
        """list_persona_ids returns sorted list."""
        ids = list_persona_ids()
        assert ids == sorted(ids)
        assert len(ids) == 5

    def test_get_persona_by_id(self) -> None:
        """Each persona is retrievable by its ID."""
        for persona in ALL_PERSONAS:
            retrieved = get_persona(persona.persona_id)
            assert retrieved is persona

    def test_get_persona_unknown_raises_key_error(self) -> None:
        """Unknown persona ID raises KeyError with helpful message."""
        with pytest.raises(KeyError, match="Unknown persona"):
            get_persona("nonexistent_persona")

    def test_get_persona_error_lists_available(self) -> None:
        """KeyError message includes available persona IDs."""
        with pytest.raises(KeyError, match="beginner_runner"):
            get_persona("nonexistent_persona")

    def test_get_persona_empty_id_raises(self) -> None:
        """Empty string persona ID raises KeyError."""
        with pytest.raises(KeyError, match="Unknown persona"):
            get_persona("")

    def test_expected_persona_ids(self) -> None:
        """The 5 personas match the PRD specification."""
        expected_ids = {
            "beginner_runner",
            "overtrained_athlete",
            "aggressive_spiker",
            "injury_prone_runner",
            "advanced_marathoner",
        }
        actual_ids = {p.persona_id for p in ALL_PERSONAS}
        assert actual_ids == expected_ids


# ---------------------------------------------------------------------------
# Profile validation — each persona produces a valid AthleteProfile
# ---------------------------------------------------------------------------


class TestPersonaProfiles:
    """Tests that each persona's AthleteProfile is valid and well-configured."""

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_profile_is_valid_athlete_profile(self, persona: EvaluationPersona) -> None:
        """Every persona's profile is a valid AthleteProfile (Pydantic validates)."""
        assert isinstance(persona.profile, AthleteProfile)

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_profile_has_name(self, persona: EvaluationPersona) -> None:
        """Every profile has a non-empty name."""
        assert len(persona.profile.name) > 0

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_profile_has_goal_distance(self, persona: EvaluationPersona) -> None:
        """Every profile specifies a goal distance."""
        assert len(persona.profile.goal_distance) > 0

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_profile_cache_key_is_deterministic(self, persona: EvaluationPersona) -> None:
        """Cache key is stable across calls."""
        key1 = persona.profile.cache_key()
        key2 = persona.profile.cache_key()
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex

    def test_profile_cache_keys_are_unique(self) -> None:
        """Each persona produces a unique cache key."""
        all_keys = {p.profile.cache_key() for p in ALL_PERSONAS}
        assert len(all_keys) == len(ALL_PERSONAS)

    def test_beginner_is_conservative(self) -> None:
        """Beginner runner has conservative risk tolerance."""
        assert BEGINNER_RUNNER.profile.risk_tolerance == RiskTolerance.CONSERVATIVE

    def test_beginner_low_mileage(self) -> None:
        """Beginner runs 5-15 km/week (PRD: 5-8 mpw ~ 8-13 km)."""
        assert 5.0 <= BEGINNER_RUNNER.profile.weekly_mileage_base <= 15.0

    def test_beginner_trains_3_days(self) -> None:
        """Beginner only trains 3 days per week."""
        assert BEGINNER_RUNNER.profile.training_days_per_week == 3

    def test_overtrained_high_base_mileage(self) -> None:
        """Overtrained athlete has a high base that needs reducing."""
        assert OVERTRAINED_ATHLETE.profile.weekly_mileage_base >= 70.0

    def test_overtrained_has_fatigue_history(self) -> None:
        """Overtrained athlete's injury history mentions fatigue."""
        assert "fatigue" in OVERTRAINED_ATHLETE.profile.injury_history.lower()

    def test_overtrained_conservative_increase(self) -> None:
        """Overtrained should have very conservative weekly increase."""
        assert OVERTRAINED_ATHLETE.profile.max_weekly_increase_pct <= 0.05

    def test_aggressive_spiker_high_increase_pct(self) -> None:
        """Aggressive spiker requests the max 20% weekly increase."""
        assert AGGRESSIVE_SPIKER.profile.max_weekly_increase_pct == 0.20

    def test_aggressive_spiker_low_base_high_goal(self) -> None:
        """Aggressive spiker has low base (30km) with marathon goal — the unsafe combo."""
        assert AGGRESSIVE_SPIKER.profile.weekly_mileage_base <= 35.0
        assert AGGRESSIVE_SPIKER.profile.goal_distance == "marathon"

    def test_injury_prone_has_detailed_history(self) -> None:
        """Injury-prone runner has multiple documented injuries."""
        history = INJURY_PRONE_RUNNER.profile.injury_history.lower()
        assert "it-band" in history or "it band" in history
        assert "shin splints" in history
        assert "plantar" in history

    def test_injury_prone_targets_ultra(self) -> None:
        """Injury-prone runner is training for 50K ultra."""
        assert INJURY_PRONE_RUNNER.profile.goal_distance == "50K"

    def test_advanced_marathoner_high_base(self) -> None:
        """Advanced marathoner has 100+ km/week base."""
        assert ADVANCED_MARATHONER.profile.weekly_mileage_base >= 100.0

    def test_advanced_marathoner_high_vdot(self) -> None:
        """Advanced marathoner has elite VDOT."""
        assert ADVANCED_MARATHONER.profile.vdot is not None
        assert ADVANCED_MARATHONER.profile.vdot >= 55.0

    def test_advanced_marathoner_sub_3_goal(self) -> None:
        """Advanced marathoner targets sub-2:50 (170 min)."""
        assert ADVANCED_MARATHONER.profile.goal_time_minutes is not None
        assert ADVANCED_MARATHONER.profile.goal_time_minutes <= 180.0


# ---------------------------------------------------------------------------
# Expected behavior completeness
# ---------------------------------------------------------------------------


class TestExpectedBehavior:
    """Tests that expected behaviors are well-defined for evaluation."""

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_has_description(self, persona: EvaluationPersona) -> None:
        """Every persona has a non-empty behavior description."""
        assert len(persona.expected_behavior.description) > 20

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_has_notes(self, persona: EvaluationPersona) -> None:
        """Every persona has evaluation notes."""
        assert len(persona.expected_behavior.notes) > 0

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_max_acwr_within_hard_limit(self, persona: EvaluationPersona) -> None:
        """No persona allows ACWR above the system hard limit of 1.5."""
        assert persona.expected_behavior.max_acwr <= 1.5

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_min_safety_score_is_reasonable(self, persona: EvaluationPersona) -> None:
        """Min safety score is at least 70 (the pass threshold)."""
        assert persona.expected_behavior.min_safety_score >= 70.0

    @pytest.mark.parametrize(
        "persona",
        ALL_PERSONAS,
        ids=[p.persona_id for p in ALL_PERSONAS],
    )
    def test_increase_pct_matches_profile(self, persona: EvaluationPersona) -> None:
        """Expected max increase matches the profile's setting."""
        assert (
            persona.expected_behavior.max_weekly_increase_pct
            == persona.profile.max_weekly_increase_pct
        )

    def test_overtrained_expects_load_reduction(self) -> None:
        """Overtrained persona expects the plan to reduce load."""
        assert OVERTRAINED_ATHLETE.expected_behavior.expect_load_reduction is True

    def test_aggressive_expects_rejection(self) -> None:
        """Aggressive spiker expects the system to push back."""
        assert AGGRESSIVE_SPIKER.expected_behavior.expect_rejection_of_request is True

    def test_beginner_expects_extra_rest(self) -> None:
        """Beginner expects at least 2 rest days per week."""
        assert BEGINNER_RUNNER.expected_behavior.min_rest_days_per_week >= 2

    def test_injury_prone_expects_cross_training(self) -> None:
        """Injury-prone runner expects cross-training in the plan."""
        assert "cross-training" in INJURY_PRONE_RUNNER.expected_behavior.must_include

    def test_injury_prone_expects_knee_mention(self) -> None:
        """Injury-prone runner expects the plan to reference current knee issue."""
        assert "knee" in INJURY_PRONE_RUNNER.expected_behavior.must_include

    def test_advanced_expects_taper(self) -> None:
        """Advanced marathoner expects taper in the plan."""
        assert "taper" in ADVANCED_MARATHONER.expected_behavior.must_include

    def test_beginner_no_speed_work(self) -> None:
        """Beginner should not have VO2max intervals."""
        assert any(
            "VO2max" in item
            for item in BEGINNER_RUNNER.expected_behavior.must_not_include
        )

    def test_overtrained_no_intensity(self) -> None:
        """Overtrained athlete should not have speed work or intervals."""
        must_not = OVERTRAINED_ATHLETE.expected_behavior.must_not_include
        assert "speed work" in must_not
        assert "interval" in must_not
        assert "tempo" in must_not


# ---------------------------------------------------------------------------
# ExpectedBehavior defaults and immutability
# ---------------------------------------------------------------------------


class TestExpectedBehaviorDefaults:
    """Tests for ExpectedBehavior dataclass default values."""

    def test_defaults(self) -> None:
        """Default values are sensible."""
        eb = ExpectedBehavior(description="test")
        assert eb.must_include == ()
        assert eb.must_not_include == ()
        assert eb.max_weekly_increase_pct == 0.10
        assert eb.min_rest_days_per_week == 1
        assert eb.expect_load_reduction is False
        assert eb.expect_rejection_of_request is False
        assert eb.max_acwr == 1.5
        assert eb.min_safety_score == 70.0
        assert eb.notes == ""

    def test_frozen(self) -> None:
        """ExpectedBehavior is immutable."""
        eb = ExpectedBehavior(description="test")
        with pytest.raises(AttributeError):
            eb.description = "changed"

    def test_must_include_is_tuple(self) -> None:
        """must_include uses tuple for true immutability inside frozen dataclass."""
        assert isinstance(BEGINNER_RUNNER.expected_behavior.must_include, tuple)

    def test_must_not_include_is_tuple(self) -> None:
        """must_not_include uses tuple for true immutability inside frozen dataclass."""
        assert isinstance(BEGINNER_RUNNER.expected_behavior.must_not_include, tuple)

    def test_evaluation_persona_frozen(self) -> None:
        """EvaluationPersona is immutable."""
        with pytest.raises(AttributeError):
            BEGINNER_RUNNER.persona_id = "changed"
