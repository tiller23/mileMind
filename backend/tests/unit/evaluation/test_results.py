"""Tests for evaluation result models and metrics aggregation."""

from datetime import datetime, timezone

import pytest

from src.evaluation.results import (
    MODEL_PRICING,
    HarnessMetrics,
    PersonaResult,
    _rates_for_model,
)
from src.models.decision_log import ReviewerScores


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
