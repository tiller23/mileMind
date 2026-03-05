"""Tests for decision log models (Phase 3 data layer)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.decision_log import (
    REVIEW_PASS_THRESHOLD,
    DecisionLogEntry,
    ReviewDimension,
    ReviewerScores,
    ReviewOutcome,
)


# ---------------------------------------------------------------------------
# ReviewDimension
# ---------------------------------------------------------------------------

class TestReviewPassThreshold:
    """Guard tests for the REVIEW_PASS_THRESHOLD constant."""

    def test_threshold_value(self) -> None:
        """Tripwire: changing this requires updating REVIEWER_SYSTEM_PROMPT."""
        assert REVIEW_PASS_THRESHOLD == 70

    def test_importable_from_package(self) -> None:
        from src.models import REVIEW_PASS_THRESHOLD as imported
        assert imported == 70


class TestReviewDimension:
    """Tests for the ReviewDimension enum."""

    def test_values(self) -> None:
        assert ReviewDimension.SAFETY == "safety"
        assert ReviewDimension.PROGRESSION == "progression"
        assert ReviewDimension.SPECIFICITY == "specificity"
        assert ReviewDimension.FEASIBILITY == "feasibility"

    def test_all_four_members(self) -> None:
        assert len(ReviewDimension) == 4


# ---------------------------------------------------------------------------
# ReviewerScores
# ---------------------------------------------------------------------------

class TestReviewerScores:
    """Tests for ReviewerScores model and computed properties."""

    def test_all_perfect(self) -> None:
        scores = ReviewerScores(safety=100, progression=100, specificity=100, feasibility=100)
        assert scores.overall == 100.0
        assert scores.all_pass is True

    def test_all_zero(self) -> None:
        scores = ReviewerScores(safety=0, progression=0, specificity=0, feasibility=0)
        assert scores.overall == 0.0
        assert scores.all_pass is False

    def test_weighted_average_safety_2x(self) -> None:
        """Safety=100, others=0 -> (200+0+0+0)/5 = 40."""
        scores = ReviewerScores(safety=100, progression=0, specificity=0, feasibility=0)
        assert scores.overall == pytest.approx(40.0)

    def test_weighted_average_non_safety(self) -> None:
        """Safety=0, progression=100, others=0 -> (0+100+0+0)/5 = 20."""
        scores = ReviewerScores(safety=0, progression=100, specificity=0, feasibility=0)
        assert scores.overall == pytest.approx(20.0)

    def test_weighted_average_mixed(self) -> None:
        """Safety=80, progression=70, specificity=90, feasibility=60 -> (160+70+90+60)/5 = 76."""
        scores = ReviewerScores(safety=80, progression=70, specificity=90, feasibility=60)
        assert scores.overall == pytest.approx(76.0)

    def test_all_pass_at_threshold(self) -> None:
        scores = ReviewerScores(safety=70, progression=70, specificity=70, feasibility=70)
        assert scores.all_pass is True

    def test_all_pass_one_below_threshold(self) -> None:
        scores = ReviewerScores(safety=70, progression=69, specificity=70, feasibility=70)
        assert scores.all_pass is False

    def test_all_pass_safety_below(self) -> None:
        scores = ReviewerScores(safety=69, progression=100, specificity=100, feasibility=100)
        assert scores.all_pass is False

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerScores(safety=-1, progression=50, specificity=50, feasibility=50)

    def test_score_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerScores(safety=101, progression=50, specificity=50, feasibility=50)

    def test_missing_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReviewerScores(safety=80, progression=80, specificity=80)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ReviewOutcome
# ---------------------------------------------------------------------------

class TestReviewOutcome:
    """Tests for the ReviewOutcome enum."""

    def test_values(self) -> None:
        assert ReviewOutcome.APPROVED == "approved"
        assert ReviewOutcome.REJECTED == "rejected"
        assert ReviewOutcome.ERROR == "error"

    def test_all_three_members(self) -> None:
        assert len(ReviewOutcome) == 3


# ---------------------------------------------------------------------------
# DecisionLogEntry
# ---------------------------------------------------------------------------

class TestDecisionLogEntry:
    """Tests for DecisionLogEntry model."""

    def test_minimal_entry(self) -> None:
        entry = DecisionLogEntry(iteration=1, outcome=ReviewOutcome.APPROVED)
        assert entry.iteration == 1
        assert entry.outcome == ReviewOutcome.APPROVED
        assert entry.scores is None
        assert entry.critique == ""
        assert entry.issues == []
        assert entry.planner_input_tokens == 0
        assert entry.reviewer_input_tokens == 0

    def test_full_entry(self) -> None:
        scores = ReviewerScores(safety=85, progression=78, specificity=90, feasibility=72)
        entry = DecisionLogEntry(
            iteration=2,
            outcome=ReviewOutcome.REJECTED,
            scores=scores,
            critique="Weekly load increase too aggressive in week 5.",
            issues=["Week 5 load increase exceeds 10%", "Missing step-back week"],
            planner_input_tokens=5000,
            planner_output_tokens=2000,
            reviewer_input_tokens=4000,
            reviewer_output_tokens=1500,
            planner_tool_calls=12,
            reviewer_tool_calls=3,
        )
        assert entry.scores is not None
        assert entry.scores.overall == pytest.approx((85 * 2 + 78 + 90 + 72) / 5)
        assert len(entry.issues) == 2
        assert entry.planner_tool_calls == 12

    def test_timestamp_auto_generated(self) -> None:
        before = datetime.now(timezone.utc)
        entry = DecisionLogEntry(iteration=1, outcome=ReviewOutcome.APPROVED)
        after = datetime.now(timezone.utc)
        assert before <= entry.timestamp <= after

    def test_iteration_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLogEntry(iteration=0, outcome=ReviewOutcome.APPROVED)

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLogEntry(
                iteration=1,
                outcome=ReviewOutcome.APPROVED,
                planner_input_tokens=-1,
            )

    def test_error_outcome(self) -> None:
        entry = DecisionLogEntry(
            iteration=3,
            outcome=ReviewOutcome.ERROR,
            critique="Reviewer failed to parse plan text.",
        )
        assert entry.outcome == ReviewOutcome.ERROR
        assert entry.scores is None

    def test_serialization_roundtrip(self) -> None:
        scores = ReviewerScores(safety=80, progression=75, specificity=85, feasibility=70)
        entry = DecisionLogEntry(
            iteration=1,
            outcome=ReviewOutcome.REJECTED,
            scores=scores,
            critique="Needs more rest days.",
            issues=["Insufficient rest"],
        )
        data = entry.model_dump()
        restored = DecisionLogEntry.model_validate(data)
        assert restored.scores is not None
        assert restored.scores.overall == scores.overall
        assert restored.issues == entry.issues


# ---------------------------------------------------------------------------
# Re-export from models package
# ---------------------------------------------------------------------------

class TestModelsReExport:
    """Verify decision_log models are accessible from src.models."""

    def test_importable_from_package(self) -> None:
        from src.models import (
            DecisionLogEntry,
            ReviewDimension,
            ReviewerScores,
            ReviewOutcome,
        )
        assert DecisionLogEntry is not None
        assert ReviewDimension is not None
        assert ReviewerScores is not None
        assert ReviewOutcome is not None
