"""Integration tests for the evaluation harness runner.

Tests HarnessRunner with a mock transport to verify it correctly
wires personas through the orchestrator and collects results.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.orchestrator import OrchestrationResult
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.evaluation.personas import ALL_PERSONAS, BEGINNER_RUNNER, get_persona
from src.evaluation.results import PersonaResult
from src.evaluation.runner import HarnessRunner
from src.models.decision_log import (
    DecisionLogEntry,
    ReviewerScores,
    ReviewOutcome,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orch_result(
    plan_text: str = "Generated plan.",
    approved: bool = True,
    scores: dict | None = None,
    planner_input: int = 50_000,
    planner_output: int = 5_000,
    reviewer_input: int = 30_000,
    reviewer_output: int = 3_000,
    iterations: int = 1,
    elapsed: float = 12.0,
) -> OrchestrationResult:
    """Build an OrchestrationResult for testing."""
    score_vals = scores or {"safety": 85, "progression": 80, "specificity": 80, "feasibility": 75}
    reviewer_scores = ReviewerScores(**score_vals)

    return OrchestrationResult(
        plan_text=plan_text,
        approved=approved,
        decision_log=[
            DecisionLogEntry(
                iteration=1,
                outcome=ReviewOutcome.APPROVED if approved else ReviewOutcome.REJECTED,
                scores=reviewer_scores,
                planner_input_tokens=planner_input,
                planner_output_tokens=planner_output,
                reviewer_input_tokens=reviewer_input,
                reviewer_output_tokens=reviewer_output,
            ),
        ],
        total_iterations=iterations,
        total_planner_input_tokens=planner_input,
        total_planner_output_tokens=planner_output,
        total_reviewer_input_tokens=reviewer_input,
        total_reviewer_output_tokens=reviewer_output,
        total_elapsed_seconds=elapsed,
        final_scores=reviewer_scores,
        athlete_cache_key="abc123def456",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHarnessRunnerSinglePersona:
    """Tests for running a single persona."""

    @pytest.mark.asyncio
    async def test_run_persona_returns_persona_result(self) -> None:
        """run_persona returns a PersonaResult with correct fields."""
        runner = HarnessRunner(
            api_key="test-key",
            transport=MagicMock(),
        )

        orch_result = _make_orch_result()

        with patch.object(
            runner, "_build_orchestrator",
        ) as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            result = await runner.run_persona(BEGINNER_RUNNER)

        assert isinstance(result, PersonaResult)
        assert result.persona_id == "beginner_runner"
        assert result.plan_text == "Generated plan."
        assert result.approved is True
        assert result.planner_input_tokens == 50_000
        assert result.reviewer_input_tokens == 30_000
        assert result.elapsed_seconds > 0
        assert result.athlete_cache_key == "abc123def456"

    @pytest.mark.asyncio
    async def test_run_persona_captures_scores(self) -> None:
        """Scores are correctly transferred from OrchestrationResult."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())
        orch_result = _make_orch_result(
            scores={"safety": 92, "progression": 88, "specificity": 85, "feasibility": 80},
        )

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            result = await runner.run_persona(BEGINNER_RUNNER)

        assert result.final_scores is not None
        assert result.final_scores.safety == 92

    @pytest.mark.asyncio
    async def test_run_persona_captures_decision_log(self) -> None:
        """Decision log is preserved in PersonaResult."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())
        orch_result = _make_orch_result()

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            result = await runner.run_persona(BEGINNER_RUNNER)

        assert len(result.decision_log) == 1

    @pytest.mark.asyncio
    async def test_run_persona_handles_exception(self) -> None:
        """Exceptions during orchestration are captured in the result."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(side_effect=RuntimeError("API down"))
            mock_build.return_value = mock_orch

            result = await runner.run_persona(BEGINNER_RUNNER)

        assert result.persona_id == "beginner_runner"
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_run_persona_sets_model_names(self) -> None:
        """Model names are set on the result for cost calculation."""
        runner = HarnessRunner(
            api_key="test-key",
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
            transport=MagicMock(),
        )
        orch_result = _make_orch_result()

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            result = await runner.run_persona(BEGINNER_RUNNER)

        assert result.planner_model == "claude-sonnet-4-20250514"
        assert result.reviewer_model == "claude-opus-4-20250514"


class TestHarnessRunnerAll:
    """Tests for running all personas."""

    @pytest.mark.asyncio
    async def test_run_all_returns_five_results(self) -> None:
        """run_all with no filter returns 5 results."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())
        orch_result = _make_orch_result()

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            results = await runner.run_all()

        assert len(results) == 5
        persona_ids = {r.persona_id for r in results}
        assert persona_ids == {p.persona_id for p in ALL_PERSONAS}

    @pytest.mark.asyncio
    async def test_run_all_with_filter(self) -> None:
        """run_all with persona filter only runs selected personas."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())
        orch_result = _make_orch_result()

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            results = await runner.run_all(persona_ids=["beginner_runner", "advanced_marathoner"])

        assert len(results) == 2
        assert results[0].persona_id == "beginner_runner"
        assert results[1].persona_id == "advanced_marathoner"

    @pytest.mark.asyncio
    async def test_run_all_invalid_persona_raises(self) -> None:
        """run_all with unknown persona ID raises KeyError."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())

        with pytest.raises(KeyError, match="Unknown persona"):
            await runner.run_all(persona_ids=["nonexistent"])


class TestHarnessRunnerComparison:
    """Tests for the Sonnet-vs-Opus comparison mode."""

    @pytest.mark.asyncio
    async def test_comparison_returns_results_per_model(self) -> None:
        """run_comparison returns a dict keyed by reviewer model."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())
        orch_result = _make_orch_result()

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            comparison = await runner.run_comparison(
                reviewer_models=["model-a", "model-b"],
                persona_ids=["beginner_runner"],
            )

        assert "model-a" in comparison
        assert "model-b" in comparison
        assert len(comparison["model-a"]) == 1
        assert len(comparison["model-b"]) == 1

    @pytest.mark.asyncio
    async def test_comparison_default_models(self) -> None:
        """Default comparison uses Opus and Sonnet."""
        runner = HarnessRunner(api_key="test-key", transport=MagicMock())
        orch_result = _make_orch_result()

        with patch.object(runner, "_build_orchestrator") as mock_build:
            mock_orch = AsyncMock()
            mock_orch.generate_plan = AsyncMock(return_value=orch_result)
            mock_build.return_value = mock_orch

            comparison = await runner.run_comparison(
                persona_ids=["beginner_runner"],
            )

        assert "claude-opus-4-20250514" in comparison
        assert "claude-sonnet-4-20250514" in comparison


class TestHarnessRunnerMetrics:
    """Tests for compute_metrics."""

    def test_compute_metrics_aggregates(self) -> None:
        """compute_metrics produces correct HarnessMetrics."""
        runner = HarnessRunner(
            api_key="test-key",
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
            transport=MagicMock(),
        )

        results = [
            PersonaResult(
                persona_id="a",
                approved=True,
                retry_count=1,
                final_scores=ReviewerScores(safety=90, progression=85, specificity=80, feasibility=80),
                planner_input_tokens=50_000,
                planner_output_tokens=5_000,
            ),
            PersonaResult(
                persona_id="b",
                approved=True,
                retry_count=2,
                final_scores=ReviewerScores(safety=80, progression=75, specificity=75, feasibility=70),
                planner_input_tokens=60_000,
                planner_output_tokens=6_000,
            ),
        ]

        metrics = runner.compute_metrics(results, total_elapsed_seconds=30.0)

        assert metrics.total_personas == 2
        assert metrics.total_approved == 2
        assert metrics.avg_retry_count == pytest.approx(1.5)
        assert metrics.avg_safety_score == pytest.approx(85.0)
        assert metrics.total_elapsed_seconds == pytest.approx(30.0)
        assert metrics.planner_model == "claude-sonnet-4-20250514"
        assert metrics.reviewer_model == "claude-opus-4-20250514"
