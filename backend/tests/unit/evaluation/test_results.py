"""Tests for evaluation result models and metrics aggregation."""

import json
from datetime import datetime, timezone

import pytest

from src.evaluation.results import (
    MODEL_PRICING,
    HarnessMetrics,
    PersonaResult,
    _rates_for_model,
)
from src.models.decision_log import DecisionLogEntry, ReviewerScores, ReviewOutcome


# ---------------------------------------------------------------------------
# Model pricing lookup
# ---------------------------------------------------------------------------


class TestModelPricing:
    """Tests for model pricing lookup."""

    def test_sonnet_rates(self) -> None:
        """Sonnet model resolves to Sonnet pricing."""
        rates = _rates_for_model("claude-sonnet-4-20250514")
        assert rates == MODEL_PRICING["claude-sonnet"]

    def test_opus_rates(self) -> None:
        """Opus model resolves to Opus pricing."""
        rates = _rates_for_model("claude-opus-4-20250514")
        assert rates == MODEL_PRICING["claude-opus"]

    def test_haiku_rates(self) -> None:
        """Haiku model resolves to Haiku pricing."""
        rates = _rates_for_model("claude-haiku-4-5-20251001")
        assert rates == MODEL_PRICING["claude-haiku"]

    def test_unknown_model_falls_back_to_sonnet(self) -> None:
        """Unknown model falls back to Sonnet rates."""
        rates = _rates_for_model("some-unknown-model")
        assert rates == MODEL_PRICING["claude-sonnet"]

    def test_pricing_dict_has_expected_models(self) -> None:
        """MODEL_PRICING contains all expected model prefixes."""
        assert "claude-sonnet" in MODEL_PRICING
        assert "claude-opus" in MODEL_PRICING
        assert "claude-haiku" in MODEL_PRICING


# ---------------------------------------------------------------------------
# PersonaResult
# ---------------------------------------------------------------------------


class TestPersonaResult:
    """Tests for the PersonaResult dataclass."""

    def test_total_tokens(self) -> None:
        """Total tokens sums all four token counters."""
        r = PersonaResult(
            persona_id="test",
            planner_input_tokens=1000,
            planner_output_tokens=500,
            reviewer_input_tokens=2000,
            reviewer_output_tokens=300,
        )
        assert r.total_tokens == 3800

    def test_total_tokens_default_zero(self) -> None:
        """Default tokens are all zero."""
        r = PersonaResult(persona_id="test")
        assert r.total_tokens == 0

    def test_estimated_cost_sonnet_planner(self) -> None:
        """Cost estimate with Sonnet planner tokens."""
        r = PersonaResult(
            persona_id="test",
            planner_input_tokens=100_000,
            planner_output_tokens=10_000,
            planner_model="claude-sonnet-4-20250514",
        )
        # Sonnet: input $3/M, output $15/M
        expected = 100_000 * 3.0 / 1_000_000 + 10_000 * 15.0 / 1_000_000
        assert r.estimated_cost_usd == pytest.approx(expected)

    def test_estimated_cost_with_opus_reviewer(self) -> None:
        """Cost estimate with Opus reviewer tokens."""
        r = PersonaResult(
            persona_id="test",
            planner_input_tokens=50_000,
            planner_output_tokens=5_000,
            reviewer_input_tokens=30_000,
            reviewer_output_tokens=3_000,
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
        )
        planner = 50_000 * 3.0 / 1_000_000 + 5_000 * 15.0 / 1_000_000
        reviewer = 30_000 * 15.0 / 1_000_000 + 3_000 * 75.0 / 1_000_000
        assert r.estimated_cost_usd == pytest.approx(planner + reviewer)

    def test_estimated_cost_sonnet_as_reviewer(self) -> None:
        """Cost estimate when Sonnet is used as reviewer (key Phase 4 comparison)."""
        r = PersonaResult(
            persona_id="test",
            planner_input_tokens=50_000,
            planner_output_tokens=5_000,
            reviewer_input_tokens=30_000,
            reviewer_output_tokens=3_000,
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-sonnet-4-20250514",
        )
        # Both use Sonnet rates
        total = (
            (50_000 + 30_000) * 3.0 / 1_000_000
            + (5_000 + 3_000) * 15.0 / 1_000_000
        )
        assert r.estimated_cost_usd == pytest.approx(total)

    def test_estimated_cost_zero_tokens(self) -> None:
        """Zero tokens means zero cost."""
        r = PersonaResult(persona_id="test")
        assert r.estimated_cost_usd == 0.0

    def test_estimated_cost_default_models_use_sonnet_opus(self) -> None:
        """Empty model strings fall back to Sonnet planner + Opus reviewer."""
        r = PersonaResult(
            persona_id="test",
            planner_input_tokens=1_000_000,
            reviewer_input_tokens=1_000_000,
        )
        # Default: Sonnet input $3/M + Opus input $15/M = $18
        assert r.estimated_cost_usd == pytest.approx(3.0 + 15.0)

    def test_has_violations_empty(self) -> None:
        """No violations by default."""
        r = PersonaResult(persona_id="test")
        assert r.has_violations is False

    def test_has_violations_with_entries(self) -> None:
        """Violations detected when list is non-empty."""
        r = PersonaResult(
            persona_id="test",
            constraint_violations=["ACWR exceeded 1.5 in week 3"],
        )
        assert r.has_violations is True

    def test_defaults(self) -> None:
        """Default field values are sensible."""
        r = PersonaResult(persona_id="test")
        assert r.plan_text == ""
        assert r.approved is False
        assert r.retry_count == 0
        assert r.total_iterations == 0
        assert r.final_scores is None
        assert r.decision_log == []
        assert r.elapsed_seconds == 0.0
        assert r.constraint_violations == []
        assert r.athlete_cache_key == ""
        assert r.warning is None
        assert r.error is None
        assert r.planner_model == ""
        assert r.reviewer_model == ""

    def test_new_fields_from_orchestration_result(self) -> None:
        """Fields added to match OrchestrationResult are present and settable."""
        r = PersonaResult(
            persona_id="test",
            total_iterations=25,
            athlete_cache_key="abc123",
            decision_log=[],
        )
        assert r.total_iterations == 25
        assert r.athlete_cache_key == "abc123"
        assert r.decision_log == []


# ---------------------------------------------------------------------------
# HarnessMetrics.from_results
# ---------------------------------------------------------------------------


class TestHarnessMetrics:
    """Tests for the HarnessMetrics aggregation."""

    def _make_result(
        self,
        persona_id: str = "test",
        approved: bool = True,
        retry_count: int = 1,
        safety: int = 85,
        progression: int = 80,
        specificity: int = 75,
        feasibility: int = 80,
        planner_input: int = 50_000,
        planner_output: int = 5_000,
        reviewer_input: int = 30_000,
        reviewer_output: int = 3_000,
        violations: list[str] | None = None,
        elapsed: float = 10.0,
    ) -> PersonaResult:
        """Helper to build a PersonaResult with scores."""
        return PersonaResult(
            persona_id=persona_id,
            approved=approved,
            retry_count=retry_count,
            final_scores=ReviewerScores(
                safety=safety,
                progression=progression,
                specificity=specificity,
                feasibility=feasibility,
            ),
            planner_input_tokens=planner_input,
            planner_output_tokens=planner_output,
            reviewer_input_tokens=reviewer_input,
            reviewer_output_tokens=reviewer_output,
            constraint_violations=violations or [],
            elapsed_seconds=elapsed,
        )

    def test_empty_results(self) -> None:
        """Empty results list produces zeroed metrics."""
        m = HarnessMetrics.from_results([])
        assert m.total_personas == 0
        assert m.total_approved == 0
        assert m.violation_rate == 0.0
        assert m.avg_retry_count == 0.0
        assert m.avg_tokens == 0.0
        assert m.avg_cost_usd == 0.0

    def test_single_result(self) -> None:
        """Single result metrics match the result directly."""
        r = self._make_result(safety=90, retry_count=2)
        m = HarnessMetrics.from_results([r])
        assert m.total_personas == 1
        assert m.total_approved == 1
        assert m.avg_retry_count == pytest.approx(2.0)
        assert m.avg_safety_score == pytest.approx(90.0)
        assert m.violation_rate == pytest.approx(0.0)

    def test_multiple_results_approval_count(self) -> None:
        """Counts approved and non-approved correctly."""
        results = [
            self._make_result(persona_id="a", approved=True),
            self._make_result(persona_id="b", approved=False),
            self._make_result(persona_id="c", approved=True),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.total_personas == 3
        assert m.total_approved == 2

    def test_violation_rate(self) -> None:
        """Violation rate is fraction of personas with violations."""
        results = [
            self._make_result(persona_id="a"),
            self._make_result(persona_id="b", violations=["ACWR too high"]),
            self._make_result(persona_id="c"),
            self._make_result(persona_id="d", violations=["Missing rest day"]),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.total_with_violations == 2
        assert m.violation_rate == pytest.approx(0.5)

    def test_single_result_all_violations(self) -> None:
        """100% violation rate when single result has violations."""
        r = self._make_result(violations=["bad"])
        m = HarnessMetrics.from_results([r])
        assert m.violation_rate == pytest.approx(1.0)

    def test_avg_retry_count(self) -> None:
        """Average retry count is mean across all personas."""
        results = [
            self._make_result(persona_id="a", retry_count=1),
            self._make_result(persona_id="b", retry_count=3),
            self._make_result(persona_id="c", retry_count=2),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.avg_retry_count == pytest.approx(2.0)

    def test_avg_safety_score(self) -> None:
        """Average safety score computed from scored results only."""
        results = [
            self._make_result(persona_id="a", safety=90),
            self._make_result(persona_id="b", safety=80),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.avg_safety_score == pytest.approx(85.0)

    def test_avg_overall_score(self) -> None:
        """Average overall uses weighted formula (safety 2x)."""
        r = self._make_result(safety=90, progression=80, specificity=70, feasibility=80)
        scores = r.final_scores
        assert scores is not None
        m = HarnessMetrics.from_results([r])
        assert m.avg_overall_score == pytest.approx(scores.overall)

    def test_scores_skip_unscored_results(self) -> None:
        """Results without scores are excluded from score averages."""
        scored = self._make_result(persona_id="a", safety=90)
        unscored = PersonaResult(persona_id="b")
        m = HarnessMetrics.from_results([scored, unscored])
        assert m.avg_safety_score == pytest.approx(90.0)

    def test_all_unscored(self) -> None:
        """All unscored results produce zero averages."""
        results = [PersonaResult(persona_id="a"), PersonaResult(persona_id="b")]
        m = HarnessMetrics.from_results(results)
        assert m.avg_safety_score == pytest.approx(0.0)
        assert m.avg_overall_score == pytest.approx(0.0)
        assert m.avg_tokens == pytest.approx(0.0)
        assert m.avg_cost_usd == pytest.approx(0.0)

    def test_avg_tokens(self) -> None:
        """Average tokens computed across all personas."""
        r1 = self._make_result(
            persona_id="a", planner_input=10_000, planner_output=1_000,
            reviewer_input=5_000, reviewer_output=500,
        )
        r2 = self._make_result(
            persona_id="b", planner_input=20_000, planner_output=2_000,
            reviewer_input=10_000, reviewer_output=1_000,
        )
        m = HarnessMetrics.from_results([r1, r2])
        expected_avg = (r1.total_tokens + r2.total_tokens) / 2
        assert m.avg_tokens == pytest.approx(expected_avg)

    def test_total_cost(self) -> None:
        """Total cost sums across all personas."""
        results = [
            self._make_result(persona_id="a"),
            self._make_result(persona_id="b"),
        ]
        m = HarnessMetrics.from_results(results)
        expected_per = results[0].estimated_cost_usd
        assert m.total_cost_usd == pytest.approx(expected_per * 2)
        assert m.avg_cost_usd == pytest.approx(expected_per)

    def test_model_names_passed_through(self) -> None:
        """Planner and reviewer model names stored in metrics."""
        m = HarnessMetrics.from_results(
            [],
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
        )
        assert m.planner_model == "claude-sonnet-4-20250514"
        assert m.reviewer_model == "claude-opus-4-20250514"

    def test_elapsed_seconds_passed_through(self) -> None:
        """Total elapsed seconds stored in metrics."""
        m = HarnessMetrics.from_results(
            [], total_elapsed_seconds=42.5,
        )
        assert m.total_elapsed_seconds == pytest.approx(42.5)

    def test_avg_elapsed_seconds(self) -> None:
        """Average elapsed seconds computed from per-persona times."""
        results = [
            self._make_result(persona_id="a", elapsed=5.0),
            self._make_result(persona_id="b", elapsed=15.0),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.avg_elapsed_seconds == pytest.approx(10.0)

    def test_max_elapsed_seconds(self) -> None:
        """Max elapsed seconds identifies the slowest persona."""
        results = [
            self._make_result(persona_id="a", elapsed=5.0),
            self._make_result(persona_id="b", elapsed=25.0),
            self._make_result(persona_id="c", elapsed=15.0),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.max_elapsed_seconds == pytest.approx(25.0)

    def test_timestamp_is_recent(self) -> None:
        """Timestamp is set to approximately now."""
        before = datetime.now(timezone.utc)
        m = HarnessMetrics.from_results([])
        after = datetime.now(timezone.utc)
        assert before <= m.timestamp <= after


# ---------------------------------------------------------------------------
# HarnessMetrics.summary
# ---------------------------------------------------------------------------


class TestHarnessMetricsSummary:
    """Tests for the summary formatting method."""

    def test_summary_contains_key_fields(self) -> None:
        """Summary includes all key metric labels."""
        m = HarnessMetrics(
            total_personas=5,
            total_approved=4,
            violation_rate=0.2,
            avg_retry_count=1.5,
            avg_safety_score=85.0,
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
        )
        text = m.summary()
        assert "Personas: 5" in text
        assert "Approved: 4/5" in text
        assert "20.0%" in text
        assert "sonnet" in text
        assert "opus" in text

    def test_summary_empty_results(self) -> None:
        """Summary works with default/zero values."""
        m = HarnessMetrics()
        text = m.summary()
        assert "Personas: 0" in text
        assert "Approved: 0/0" in text

    def test_summary_includes_worst_persona(self) -> None:
        """Summary includes worst persona when set."""
        m = HarnessMetrics(worst_persona_id="overtrained_athlete")
        text = m.summary()
        assert "Worst persona: overtrained_athlete" in text

    def test_summary_omits_worst_persona_when_empty(self) -> None:
        """Summary omits worst persona line when not set."""
        m = HarnessMetrics()
        text = m.summary()
        assert "Worst persona" not in text


# ---------------------------------------------------------------------------
# PersonaResult.summary
# ---------------------------------------------------------------------------


class TestPersonaResultSummary:
    """Tests for PersonaResult.summary() method."""

    def test_summary_approved(self) -> None:
        """Summary shows APPROVED status for approved results."""
        r = PersonaResult(
            persona_id="beginner_runner",
            approved=True,
            final_scores=ReviewerScores(
                safety=90, progression=85, specificity=80, feasibility=75,
            ),
            planner_input_tokens=50_000,
            planner_output_tokens=5_000,
            reviewer_input_tokens=30_000,
            reviewer_output_tokens=3_000,
            elapsed_seconds=12.5,
        )
        text = r.summary()
        assert "Persona: beginner_runner" in text
        assert "Status: APPROVED" in text
        assert "safety=90" in text
        assert "progression=85" in text
        assert "specificity=80" in text
        assert "feasibility=75" in text
        assert "overall=" in text
        assert "Tokens: 88,000" in text
        assert "planner: 55,000" in text
        assert "reviewer: 33,000" in text
        assert "Cost: $" in text
        assert "Time: 12.5s" in text
        assert "Violations: 0" in text

    def test_summary_rejected(self) -> None:
        """Summary shows REJECTED status for rejected results."""
        r = PersonaResult(
            persona_id="aggressive_spiker",
            approved=False,
            final_scores=ReviewerScores(
                safety=60, progression=70, specificity=65, feasibility=55,
            ),
            constraint_violations=["Missing required phrase: 'safe'"],
        )
        text = r.summary()
        assert "Status: REJECTED" in text
        assert "Violations: 1" in text

    def test_summary_error(self) -> None:
        """Summary shows ERROR status when error field is set."""
        r = PersonaResult(
            persona_id="test",
            error="RuntimeError: API timeout",
        )
        text = r.summary()
        assert "Status: ERROR" in text

    def test_summary_no_scores(self) -> None:
        """Summary handles None scores gracefully."""
        r = PersonaResult(persona_id="test")
        text = r.summary()
        assert "Scores: N/A" in text


# ---------------------------------------------------------------------------
# PersonaResult.to_dict
# ---------------------------------------------------------------------------


class TestPersonaResultToDict:
    """Tests for PersonaResult.to_dict() method."""

    def test_to_dict_basic(self) -> None:
        """to_dict returns a JSON-serializable dict with all fields."""
        r = PersonaResult(
            persona_id="beginner_runner",
            plan_text="Week 1: Easy run",
            approved=True,
            retry_count=1,
            planner_input_tokens=50_000,
            planner_output_tokens=5_000,
            reviewer_input_tokens=30_000,
            reviewer_output_tokens=3_000,
            elapsed_seconds=10.0,
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
            final_scores=ReviewerScores(
                safety=90, progression=85, specificity=80, feasibility=75,
            ),
        )
        d = r.to_dict()

        assert d["persona_id"] == "beginner_runner"
        assert d["plan_text"] == "Week 1: Easy run"
        assert d["approved"] is True
        assert d["retry_count"] == 1
        assert d["total_tokens"] == 88_000
        assert d["final_scores"]["safety"] == 90
        assert d["final_scores"]["overall"] == pytest.approx(
            (90 * 2 + 85 + 80 + 75) / 5,
        )
        assert d["estimated_cost_usd"] == pytest.approx(r.estimated_cost_usd)

        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert json_str  # non-empty

    def test_to_dict_no_scores(self) -> None:
        """to_dict handles None final_scores."""
        r = PersonaResult(persona_id="test")
        d = r.to_dict()
        assert d["final_scores"] is None

    def test_to_dict_with_decision_log(self) -> None:
        """to_dict includes decision log entries as dicts."""
        entry = DecisionLogEntry(
            iteration=1,
            outcome=ReviewOutcome.APPROVED,
            scores=ReviewerScores(
                safety=85, progression=80, specificity=75, feasibility=70,
            ),
        )
        r = PersonaResult(
            persona_id="test",
            decision_log=[entry],
        )
        d = r.to_dict()
        assert len(d["decision_log"]) == 1
        assert d["decision_log"][0]["iteration"] == 1
        assert d["decision_log"][0]["outcome"] == "approved"

        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert json_str

    def test_to_dict_includes_error_and_warning(self) -> None:
        """to_dict includes error and warning fields."""
        r = PersonaResult(
            persona_id="test",
            error="Something failed",
            warning="Budget exceeded",
        )
        d = r.to_dict()
        assert d["error"] == "Something failed"
        assert d["warning"] == "Budget exceeded"


# ---------------------------------------------------------------------------
# HarnessMetrics.to_dict
# ---------------------------------------------------------------------------


class TestHarnessMetricsToDict:
    """Tests for HarnessMetrics.to_dict() method."""

    def test_to_dict_basic(self) -> None:
        """to_dict returns a JSON-serializable dict with ISO timestamp."""
        m = HarnessMetrics(
            total_personas=5,
            total_approved=4,
            violation_rate=0.2,
            total_cost_usd=2.50,
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
            worst_persona_id="overtrained_athlete",
        )
        d = m.to_dict()

        assert d["total_personas"] == 5
        assert d["total_approved"] == 4
        assert d["violation_rate"] == pytest.approx(0.2)
        assert d["total_cost_usd"] == pytest.approx(2.50)
        assert d["worst_persona_id"] == "overtrained_athlete"
        assert isinstance(d["timestamp"], str)
        assert "T" in d["timestamp"]  # ISO format

        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert json_str

    def test_to_dict_empty(self) -> None:
        """to_dict works with default values."""
        m = HarnessMetrics()
        d = m.to_dict()
        assert d["total_personas"] == 0
        assert d["worst_persona_id"] == ""

        json_str = json.dumps(d)
        assert json_str


# ---------------------------------------------------------------------------
# HarnessMetrics.worst_persona_id
# ---------------------------------------------------------------------------


class TestWorstPersonaId:
    """Tests for worst_persona_id computation in from_results."""

    def _make_result(
        self,
        persona_id: str,
        safety: int = 85,
        progression: int = 80,
        specificity: int = 75,
        feasibility: int = 80,
    ) -> PersonaResult:
        """Helper to build a scored PersonaResult."""
        return PersonaResult(
            persona_id=persona_id,
            final_scores=ReviewerScores(
                safety=safety,
                progression=progression,
                specificity=specificity,
                feasibility=feasibility,
            ),
        )

    def test_worst_persona_lowest_overall(self) -> None:
        """worst_persona_id is the persona with the lowest overall score."""
        results = [
            self._make_result("good", safety=90, progression=90, specificity=90, feasibility=90),
            self._make_result("bad", safety=60, progression=60, specificity=60, feasibility=60),
            self._make_result("mid", safety=80, progression=80, specificity=80, feasibility=80),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.worst_persona_id == "bad"

    def test_worst_persona_tie_broken_by_safety(self) -> None:
        """When overall scores tie, lowest safety wins."""
        # overall = (safety*2 + prog + spec + feas) / 5
        # For persona_a: (80*2 + 90 + 90 + 90) / 5 = 86.0
        # For persona_b: (85*2 + 85 + 85 + 90) / 5 = 86.0  (tied overall)
        # But persona_a has lower safety (80 < 85), so it's worst
        results = [
            self._make_result("a", safety=80, progression=90, specificity=90, feasibility=90),
            self._make_result("b", safety=85, progression=85, specificity=85, feasibility=90),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.worst_persona_id == "a"

    def test_worst_persona_empty_results(self) -> None:
        """Empty results produce empty worst_persona_id."""
        m = HarnessMetrics.from_results([])
        assert m.worst_persona_id == ""

    def test_worst_persona_all_unscored(self) -> None:
        """All unscored results produce empty worst_persona_id."""
        results = [PersonaResult(persona_id="a"), PersonaResult(persona_id="b")]
        m = HarnessMetrics.from_results(results)
        assert m.worst_persona_id == ""

    def test_worst_persona_single_scored(self) -> None:
        """Single scored result is worst by default."""
        results = [self._make_result("only_one", safety=95)]
        m = HarnessMetrics.from_results(results)
        assert m.worst_persona_id == "only_one"

    def test_worst_persona_mixed_scored_unscored(self) -> None:
        """Unscored results are excluded from worst calculation."""
        results = [
            self._make_result("scored_bad", safety=60, progression=60, specificity=60, feasibility=60),
            PersonaResult(persona_id="unscored"),
            self._make_result("scored_good", safety=90, progression=90, specificity=90, feasibility=90),
        ]
        m = HarnessMetrics.from_results(results)
        assert m.worst_persona_id == "scored_bad"
