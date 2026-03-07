"""Tests for evaluation report generation."""

import pytest

from src.evaluation.report import (
    _format_comparison_persona,
    _format_persona_section,
    generate_comparison_report,
    generate_plan_review_report,
)
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
        assert "No personas were evaluated" in report
        assert "No results to display" in report

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


# ---------------------------------------------------------------------------
# S45: _format_comparison_persona with a missing persona result
# ---------------------------------------------------------------------------


class TestFormatComparisonPersonaMissingResult:
    """S45 — _format_comparison_persona produces '—' for a model missing a persona.

    WHY: In a comparison run, one reviewer model may fail or skip a persona
    while another succeeds. The function must render '—' placeholders for all
    metric cells where the result is absent rather than raising AttributeError.
    """

    def test_missing_result_produces_dash_for_all_metric_cells(self) -> None:
        """Absent result for model-b renders '—' across every metric row."""
        comparison: dict[str, list[PersonaResult]] = {
            "model-a": [_make_result(persona_id="beginner_runner", safety=88)],
            # model-b has no result for beginner_runner
            "model-b": [],
        }

        lines = _format_comparison_persona("beginner_runner", comparison)
        joined = "\n".join(lines)

        # The header and separator must be present
        assert "### beginner_runner" in joined
        # The persona was found for model-a but not model-b
        # Each metric row must contain '—' (from the None branch in each lambda)
        assert "—" in joined

    def test_missing_result_does_not_raise(self) -> None:
        """_format_comparison_persona must not raise when a model has no result.

        WHY: AttributeError on None would crash report generation mid-run,
        leaving the human reviewer with no output at all.
        """
        comparison: dict[str, list[PersonaResult]] = {
            "model-a": [_make_result(persona_id="advanced_marathoner")],
            "model-b": [],  # no result for this persona
        }

        # Must not raise
        lines = _format_comparison_persona("advanced_marathoner", comparison)
        assert lines  # non-empty output produced

    def test_both_models_missing_result_all_dashes(self) -> None:
        """When neither model has the persona, all metric cells are '—'."""
        comparison: dict[str, list[PersonaResult]] = {
            "model-a": [],
            "model-b": [],
        }

        lines = _format_comparison_persona("injury_prone_runner", comparison)
        joined = "\n".join(lines)

        # Every data row's cells must be '—' (8 metric rows × '—')
        assert joined.count("—") >= 8

    def test_present_result_shows_real_values(self) -> None:
        """When a result is present, real metric values are rendered, not '—'.

        WHY: Guard against a regression where the None branch is always taken.
        """
        comparison: dict[str, list[PersonaResult]] = {
            "model-a": [_make_result(persona_id="beginner_runner", safety=92, approved=True)],
            "model-b": [],
        }

        lines = _format_comparison_persona("beginner_runner", comparison)
        joined = "\n".join(lines)

        # Safety score 92 must appear from model-a's result
        assert "92" in joined
        # Approved "Yes" must appear
        assert "Yes" in joined


# ---------------------------------------------------------------------------
# S46: _format_persona_section with unknown persona ID
# ---------------------------------------------------------------------------


class TestFormatPersonaSectionUnknownPersona:
    """S46 — _format_persona_section handles an unrecognised persona_id gracefully.

    WHY: If a PersonaResult is built with an ad-hoc persona_id that was not
    registered in the personas module (e.g. from a future test or custom run),
    the report must not crash. It should print the placeholder text and
    continue to render the rest of the result metadata.
    """

    def test_unknown_persona_does_not_raise(self) -> None:
        """_format_persona_section must not raise KeyError for an unknown persona_id."""
        result = PersonaResult(
            persona_id="completely_unknown_persona_xyz",
            plan_text="Some plan text.",
            approved=True,
            retry_count=0,
        )

        # Must not raise
        lines = _format_persona_section(result)
        assert lines  # non-empty output produced

    def test_unknown_persona_shows_not_found_message(self) -> None:
        """Unknown persona_id produces 'Persona definition not found' in output.

        WHY: The human reviewer needs to know why the expected behavior section
        is absent so they can distinguish a system error from a genuine gap.
        """
        result = PersonaResult(
            persona_id="phantom_persona_abc",
            plan_text="Plan for phantom athlete.",
            approved=False,
            retry_count=1,
        )

        lines = _format_persona_section(result)
        joined = "\n".join(lines)

        assert "Persona definition not found" in joined

    def test_unknown_persona_still_renders_result_metadata(self) -> None:
        """Even with an unknown persona_id, result metadata is rendered.

        WHY: The persona section has two independent try/except blocks — one
        for the athlete profile and one for expected behavior. Both may fail,
        but the result metadata block (status, retries, scores) has no lookup
        and must always render.
        """
        result = PersonaResult(
            persona_id="not_registered",
            plan_text="Some plan.",
            approved=True,
            retry_count=2,
            final_scores=ReviewerScores(
                safety=80, progression=75, specificity=70, feasibility=65,
            ),
        )

        lines = _format_persona_section(result)
        joined = "\n".join(lines)

        assert "APPROVED" in joined
        assert "not_registered" in joined

    def test_known_persona_does_not_show_not_found(self) -> None:
        """Known persona_id must NOT show 'Persona definition not found'.

        WHY: Regression guard — ensures the happy path still works after the
        graceful-failure path is added.
        """
        result = PersonaResult(
            persona_id="beginner_runner",
            plan_text="Easy 5km run.",
            approved=True,
            retry_count=0,
        )

        lines = _format_persona_section(result)
        joined = "\n".join(lines)

        assert "Persona definition not found" not in joined
        assert "### Athlete Profile" in joined
