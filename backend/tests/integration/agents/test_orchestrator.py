"""Integration tests for the planner-reviewer orchestrator.

Tests the orchestration loop with mocked planner and reviewer agents.
Verifies approval flow, rejection-retry flow, max retries, validation
pre-filtering, decision log, and token tracking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.orchestrator import Orchestrator, OrchestrationResult
from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.reviewer import ReviewerAgent, ReviewerResult
from src.agents.validation import ValidationResult
from src.models.athlete import AthleteProfile, RiskTolerance
from src.models.decision_log import ReviewerScores, ReviewOutcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_athlete() -> AthleteProfile:
    """A simple athlete for testing."""
    return AthleteProfile(
        name="Test Runner",
        age=30,
        weekly_mileage_base=30.0,
        goal_distance="5K",
        goal_time_minutes=25.0,
        vdot=40.0,
        risk_tolerance=RiskTolerance.MODERATE,
        training_days_per_week=4,
    )


def _make_planner_result(
    plan_text: str = "Valid plan.",
    passed: bool = True,
    error: str | None = None,
    tool_calls: list | None = None,
    input_tokens: int = 1000,
    output_tokens: int = 500,
    iterations: int = 5,
) -> PlannerResult:
    """Helper to build a PlannerResult."""
    return PlannerResult(
        plan_text=plan_text,
        tool_calls=tool_calls or [
            {"name": "compute_training_stress", "input": {}, "output": {"tss": 30}, "success": True},
            {"name": "validate_progression_constraints", "input": {}, "output": {"valid": True}, "success": True},
        ],
        iterations=iterations,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        error=error,
        validation=ValidationResult(
            passed=passed,
            issues=[] if passed else ["Validation failed"],
        ),
    )


def _make_reviewer_result(
    approved: bool = True,
    scores: dict | None = None,
    critique: str = "Looks good.",
    issues: list[str] | None = None,
    error: str | None = None,
    input_tokens: int = 800,
    output_tokens: int = 300,
    iterations: int = 2,
) -> ReviewerResult:
    """Helper to build a ReviewerResult."""
    score_vals = scores or {"safety": 85, "progression": 80, "specificity": 80, "feasibility": 75}
    return ReviewerResult(
        approved=approved,
        scores=ReviewerScores(**score_vals),
        critique=critique,
        issues=issues or [],
        tool_calls=[],
        iterations=iterations,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        error=error,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOrchestratorApproval:
    """Tests for the happy path: approved on first attempt."""

    @pytest.mark.asyncio
    async def test_approved_first_attempt(self, sample_athlete: AthleteProfile) -> None:
        """Plan approved on first try — single planner + reviewer cycle."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result())

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=3)
        result = await orch.generate_plan(sample_athlete)

        assert result.approved is True
        assert result.plan_text == "Valid plan."
        assert len(result.decision_log) == 1
        assert result.decision_log[0].outcome == ReviewOutcome.APPROVED
        assert result.warning is None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_scores_populated(self, sample_athlete: AthleteProfile) -> None:
        """Final scores are populated from the reviewer."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result(
            scores={"safety": 92, "progression": 88, "specificity": 85, "feasibility": 80},
        ))

        orch = Orchestrator(planner=planner, reviewer=reviewer)
        result = await orch.generate_plan(sample_athlete)

        assert result.final_scores is not None
        assert result.final_scores.safety == 92


class TestOrchestratorRetry:
    """Tests for the rejection-retry flow."""

    @pytest.mark.asyncio
    async def test_retry_after_rejection(self, sample_athlete: AthleteProfile) -> None:
        """Rejected on attempt 1, approved on attempt 2."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result(plan_text="Plan v1"))
        planner.revise_plan = AsyncMock(return_value=_make_planner_result(plan_text="Plan v2"))

        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(side_effect=[
            _make_reviewer_result(
                approved=False,
                scores={"safety": 55, "progression": 80, "specificity": 80, "feasibility": 75},
                critique="Safety issues.",
                issues=["No rest days"],
            ),
            _make_reviewer_result(approved=True),
        ])

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=3)
        result = await orch.generate_plan(sample_athlete)

        assert result.approved is True
        assert result.plan_text == "Plan v2"
        assert len(result.decision_log) == 2
        assert result.decision_log[0].outcome == ReviewOutcome.REJECTED
        assert result.decision_log[1].outcome == ReviewOutcome.APPROVED

        # Verify revise_plan was called with critique
        planner.revise_plan.assert_called_once()
        call_args = planner.revise_plan.call_args
        assert call_args[0][1] == "Plan v1"  # prior_plan_text
        assert "Safety issues." in call_args[0][2]  # reviewer_critique
        assert "No rest days" in call_args[0][3]  # reviewer_issues

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, sample_athlete: AthleteProfile) -> None:
        """Plan never approved — returns last plan with warning."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result(plan_text="Plan v1"))
        planner.revise_plan = AsyncMock(return_value=_make_planner_result(plan_text="Plan v2"))

        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result(
            approved=False,
            critique="Still has issues.",
            issues=["Ongoing problem"],
        ))

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=2)
        result = await orch.generate_plan(sample_athlete)

        assert result.approved is False
        assert result.plan_text == "Plan v2"  # last valid plan
        assert result.warning is not None
        assert "2 attempts" in result.warning
        assert len(result.decision_log) == 2


class TestOrchestratorValidationPreFilter:
    """Tests for Phase 2 validation pre-filtering."""

    @pytest.mark.asyncio
    async def test_validation_failure_skips_reviewer(self, sample_athlete: AthleteProfile) -> None:
        """When planner output fails validation, reviewer is not called."""
        planner = MagicMock(spec=PlannerAgent)
        # Attempt 1: validation fails
        planner.generate_plan = AsyncMock(return_value=_make_planner_result(
            plan_text="Bad plan",
            passed=False,
            error="Output validation failed: missing tools",
        ))
        # Attempt 2: validation passes, approved
        planner.revise_plan = AsyncMock(return_value=_make_planner_result(plan_text="Fixed plan"))

        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result())

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=3)
        result = await orch.generate_plan(sample_athlete)

        assert result.approved is True
        assert result.plan_text == "Fixed plan"
        assert len(result.decision_log) == 2
        assert result.decision_log[0].outcome == ReviewOutcome.ERROR
        # Reviewer was only called once (for the fixed plan)
        assert reviewer.review_plan.call_count == 1


class TestOrchestratorDecisionLog:
    """Tests for decision log population."""

    @pytest.mark.asyncio
    async def test_decision_log_has_correct_entries(self, sample_athlete: AthleteProfile) -> None:
        """Each attempt produces exactly one decision log entry."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        planner.revise_plan = AsyncMock(return_value=_make_planner_result())

        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(side_effect=[
            _make_reviewer_result(approved=False, issues=["Fix X"]),
            _make_reviewer_result(approved=False, issues=["Fix Y"]),
            _make_reviewer_result(approved=True),
        ])

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=5)
        result = await orch.generate_plan(sample_athlete)

        assert len(result.decision_log) == 3
        assert result.decision_log[0].iteration == 1
        assert result.decision_log[1].iteration == 2
        assert result.decision_log[2].iteration == 3

    @pytest.mark.asyncio
    async def test_decision_log_tracks_tokens(self, sample_athlete: AthleteProfile) -> None:
        """Token counts are recorded per-iteration."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result(
            input_tokens=2000, output_tokens=1000,
        ))
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result(
            input_tokens=1500, output_tokens=500,
        ))

        orch = Orchestrator(planner=planner, reviewer=reviewer)
        result = await orch.generate_plan(sample_athlete)

        entry = result.decision_log[0]
        assert entry.planner_input_tokens == 2000
        assert entry.planner_output_tokens == 1000
        assert entry.reviewer_input_tokens == 1500
        assert entry.reviewer_output_tokens == 500

    @pytest.mark.asyncio
    async def test_decision_log_tracks_tool_calls(self, sample_athlete: AthleteProfile) -> None:
        """Tool call counts are recorded per-iteration."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result())

        orch = Orchestrator(planner=planner, reviewer=reviewer)
        result = await orch.generate_plan(sample_athlete)

        entry = result.decision_log[0]
        assert entry.planner_tool_calls == 2  # from _make_planner_result default
        assert entry.reviewer_tool_calls == 0  # from _make_reviewer_result default


class TestOrchestratorTokenTracking:
    """Tests for cumulative token tracking."""

    @pytest.mark.asyncio
    async def test_cumulative_tokens(self, sample_athlete: AthleteProfile) -> None:
        """Tokens accumulate across retry iterations."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result(
            input_tokens=1000, output_tokens=500,
        ))
        planner.revise_plan = AsyncMock(return_value=_make_planner_result(
            input_tokens=1200, output_tokens=600,
        ))

        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(side_effect=[
            _make_reviewer_result(approved=False, input_tokens=800, output_tokens=300),
            _make_reviewer_result(approved=True, input_tokens=900, output_tokens=350),
        ])

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=3)
        result = await orch.generate_plan(sample_athlete)

        # Planner: (1000+500) + (1200+600) = 3300
        assert result.total_planner_tokens == 3300
        # Reviewer: (800+300) + (900+350) = 2350
        assert result.total_reviewer_tokens == 2350


class TestOrchestratorReviewerError:
    """Tests for reviewer error handling."""

    @pytest.mark.asyncio
    async def test_reviewer_error_treated_as_rejection(self, sample_athlete: AthleteProfile) -> None:
        """Reviewer error is logged as ERROR and triggers retry."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        planner.revise_plan = AsyncMock(return_value=_make_planner_result(plan_text="Revised"))

        error_result = ReviewerResult(
            approved=False,
            scores=None,
            error="Could not find JSON verdict.",
        )
        ok_result = _make_reviewer_result(approved=True)

        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(side_effect=[error_result, ok_result])

        orch = Orchestrator(planner=planner, reviewer=reviewer, max_retries=3)
        result = await orch.generate_plan(sample_athlete)

        assert result.approved is True
        assert len(result.decision_log) == 2
        assert result.decision_log[0].outcome == ReviewOutcome.ERROR

    @pytest.mark.asyncio
    async def test_elapsed_time_tracked(self, sample_athlete: AthleteProfile) -> None:
        """Elapsed time is recorded."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result())

        orch = Orchestrator(planner=planner, reviewer=reviewer)
        result = await orch.generate_plan(sample_athlete)

        assert result.total_elapsed_seconds >= 0.0


class TestOrchestratorIterations:
    """Tests for iteration counting."""

    @pytest.mark.asyncio
    async def test_total_iterations_accumulate(self, sample_athlete: AthleteProfile) -> None:
        """Total iterations = sum of all planner + reviewer iterations."""
        planner = MagicMock(spec=PlannerAgent)
        planner.generate_plan = AsyncMock(return_value=_make_planner_result(iterations=5))
        reviewer = MagicMock(spec=ReviewerAgent)
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result(iterations=3))

        orch = Orchestrator(planner=planner, reviewer=reviewer)
        result = await orch.generate_plan(sample_athlete)

        assert result.total_iterations == 8  # 5 planner + 3 reviewer
