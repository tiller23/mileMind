"""Tests for evaluation report generation."""

import pytest

from src.evaluation.report import generate_comparison_report, generate_plan_review_report
from src.evaluation.results import HarnessMetrics, PersonaResult
from src.models.decision_log import DecisionLogEntry, ReviewerScores, ReviewOutcome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    persona_id: str = "beginner_runner",
    approved: bool = True,
    plan_text: str = "Week 1: Easy run 5km\nWeek 2: Easy run 6km",
    safety: int = 85,
    progression: int = 80,
    specificity: int = 75,
    feasibility: int = 80,
    retry_count: int = 1,
    violations: list[str] | None = None,
) -> PersonaResult:
    """Build a PersonaResult for testing."""
    return PersonaResult(
        persona_id=persona_id,
        plan_text=plan_text,
        approved=approved,
        retry_count=retry_count,
        final_scores=ReviewerScores(
            safety=safety,
            progression=progression,
            specificity=specificity,
            feasibility=feasibility,
        ),
        planner_input_tokens=50_000,
        planner_output_tokens=5_000,
        reviewer_input_tokens=30_000,
        reviewer_output_tokens=3_000,
        elapsed_seconds=15.0,
        constraint_violations=violations or [],
        decision_log=[
            DecisionLogEntry(
                iteration=1,
                outcome=ReviewOutcome.APPROVED if approved else ReviewOutcome.REJECTED,
                scores=ReviewerScores(
                    safety=safety,
                    progression=progression,
                    specificity=specificity,
                    feasibility=feasibility,
                ),
                critique="Looks good." if approved else "Needs work.",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Plan review report
# ---------------------------------------------------------------------------


class TestPlanReviewReport:
    """Tests for generate_plan_review_report."""

    def test_report_contains_summary_table(self) -> None:
        """Report includes the summary metrics table."""
        results = [_make_result()]
        metrics = HarnessMetrics.from_results(results, planner_model="sonnet", reviewer_model="opus")
        report = generate_plan_review_report(results, metrics)

        assert "## Summary" in report
        assert "Personas evaluated" in report
        assert "Plans approved" in report
        assert "Constraint violation rate" in report

    def test_report_contains_per_persona_table(self) -> None:
        """Report includes per-persona results table."""
        results = [
            _make_result(persona_id="beginner_runner"),
            _make_result(persona_id="advanced_marathoner"),
        ]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "## Per-Persona Results" in report
        assert "beginner_runner" in report
        assert "advanced_marathoner" in report

    def test_report_contains_plan_text_in_code_fence(self) -> None:
        """Report includes the actual generated plan text inside a code fence."""
        results = [_make_result(plan_text="My test plan content")]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "My test plan content" in report
        assert "```" in report
        assert "<details>" in report

    def test_report_contains_expected_behavior(self) -> None:
        """Report includes expected behavior from persona definitions."""
        results = [_make_result(persona_id="beginner_runner")]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "### Expected Behavior" in report
        assert "Must include:" in report
        assert "Must NOT include:" in report

    def test_report_contains_decision_log(self) -> None:
        """Report includes the decision log for each persona."""
        results = [_make_result()]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "### Decision Log" in report
        assert "Iteration 1" in report

    def test_report_shows_rejected_status(self) -> None:
        """Rejected plans are clearly marked."""
        results = [_make_result(approved=False)]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "REJECTED" in report

    def test_report_shows_violations(self) -> None:
        """Constraint violations are displayed."""
        results = [_make_result(violations=["ACWR exceeded 1.5 in week 3"])]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "ACWR exceeded 1.5 in week 3" in report

    def test_report_no_plan_text(self) -> None:
        """Empty plan text shows placeholder."""
        results = [_make_result(plan_text="")]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "*(No plan generated)*" in report

    def test_report_contains_review_instructions(self) -> None:
        """Report includes manual review instructions."""
        results = [_make_result()]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "## Review Instructions" in report
        assert "physiologically reasonable" in report

    def test_report_contains_athlete_profile(self) -> None:
        """Report includes athlete profile summary."""
        results = [_make_result(persona_id="beginner_runner")]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "### Athlete Profile" in report
        assert "**VDOT:**" in report
        assert "**Risk tolerance:**" in report

    def test_report_contains_min_safety_score(self) -> None:
        """Report summary includes min safety score."""
        results = [
            _make_result(persona_id="beginner_runner", safety=90),
            _make_result(persona_id="advanced_marathoner", safety=75),
        ]
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "Min safety score" in report
        assert "75" in report

    def test_report_empty_results(self) -> None:
        """Report handles empty result list without crashing."""
        results: list[PersonaResult] = []
        metrics = HarnessMetrics.from_results(results)
        report = generate_plan_review_report(results, metrics)

        assert "## Summary" in report
        assert "Personas evaluated" in report

    def test_report_none_scores(self) -> None:
        """Report handles result with None final_scores."""
        result = PersonaResult(
            persona_id="beginner_runner",
            plan_text="Test plan",
            approved=False,
            retry_count=0,
            final_scores=None,
        )
        metrics = HarnessMetrics.from_results([result])
        report = generate_plan_review_report([result], metrics)

        assert "beginner_runner" in report
        assert "—" in report

    def test_report_shows_model_names(self) -> None:
        """Report header shows planner and reviewer model names."""
        results = [_make_result()]
        metrics = HarnessMetrics.from_results(
            results, planner_model="claude-sonnet-4", reviewer_model="claude-opus-4",
        )
        report = generate_plan_review_report(results, metrics)

        assert "claude-sonnet-4" in report
        assert "claude-opus-4" in report


# ---------------------------------------------------------------------------
# Comparison report
# ---------------------------------------------------------------------------


class TestComparisonReport:
    """Tests for generate_comparison_report."""

    def test_comparison_has_summary_table(self) -> None:
        """Comparison report includes summary comparison table."""
        comparison = {
            "claude-opus-4": [_make_result(persona_id="beginner_runner", safety=90)],
            "claude-sonnet-4": [_make_result(persona_id="beginner_runner", safety=85)],
        }
        report = generate_comparison_report(comparison)

        assert "## Summary Comparison" in report
        assert "opus" in report
        assert "sonnet" in report

    def test_comparison_has_per_persona_section(self) -> None:
        """Comparison report includes per-persona comparison."""
        comparison = {
            "claude-opus-4": [_make_result(persona_id="beginner_runner")],
            "claude-sonnet-4": [_make_result(persona_id="beginner_runner")],
        }
        report = generate_comparison_report(comparison)

        assert "## Per-Persona Comparison" in report
        assert "### beginner_runner" in report

    def test_comparison_has_decision_guidance(self) -> None:
        """Comparison report includes decision guidance for model swap."""
        comparison = {
            "model-a": [_make_result()],
            "model-b": [_make_result()],
        }
        report = generate_comparison_report(comparison)

        assert "## Decision Guidance" in report
        assert "Switch reviewer from Opus to Sonnet if" in report

    def test_comparison_multiple_personas(self) -> None:
        """Comparison handles multiple personas per model."""
        comparison = {
            "model-a": [
                _make_result(persona_id="beginner_runner"),
                _make_result(persona_id="advanced_marathoner"),
            ],
            "model-b": [
                _make_result(persona_id="beginner_runner"),
                _make_result(persona_id="advanced_marathoner"),
            ],
        }
        report = generate_comparison_report(comparison)

        assert "### beginner_runner" in report
        assert "### advanced_marathoner" in report

    def test_comparison_shows_cost_difference(self) -> None:
        """Comparison includes cost per model."""
        comparison = {
            "model-a": [_make_result()],
            "model-b": [_make_result()],
        }
        report = generate_comparison_report(comparison)

        assert "Total cost" in report
        assert "$" in report

    def test_comparison_shows_computed_deltas(self) -> None:
        """Comparison report shows computed deltas for two models."""
        comparison = {
            "claude-opus-4": [_make_result(safety=90)],
            "claude-sonnet-4": [_make_result(safety=80)],
        }
        report = generate_comparison_report(comparison)

        assert "### Computed Deltas" in report
        assert "Approval rate match" in report
        assert "Safety score delta" in report
        assert "Cost savings" in report
