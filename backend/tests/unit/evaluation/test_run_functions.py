"""W33 — Unit tests for run_single() and run_comparison() execution paths.

Both functions are async CLI entry points in src/evaluation/run.py that wire
together HarnessRunner, report generation, and file writing. These tests mock
HarnessRunner so no real API calls are made and verify:

- run_single(): calls runner.run_all / run_all_batched, writes report to disk
- run_comparison(): calls runner.run_comparison, writes per-model reports
- report files land in the tmp_path directory
- the batch flag routes to run_all_batched instead of run_all

Mirror target: src/evaluation/run.py -> tests/unit/evaluation/test_run_functions.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.evaluation.results import HarnessMetrics, PersonaResult
from src.models.decision_log import ReviewerScores


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_persona_result(persona_id: str = "beginner_runner") -> PersonaResult:
    """Build a minimal PersonaResult for mocking harness output."""
    return PersonaResult(
        persona_id=persona_id,
        plan_text=f"Plan for {persona_id}.",
        approved=True,
        retry_count=1,
        final_scores=ReviewerScores(
            safety=85, progression=80, specificity=80, feasibility=75,
        ),
        planner_input_tokens=50_000,
        planner_output_tokens=5_000,
        reviewer_input_tokens=30_000,
        reviewer_output_tokens=3_000,
        elapsed_seconds=12.0,
        planner_model="claude-sonnet-4-20250514",
        reviewer_model="claude-opus-4-20250514",
    )


def _make_args(
    *,
    planner_model: str = "claude-sonnet-4-20250514",
    reviewer_model: str = "claude-opus-4-20250514",
    persona: list[str] | None = None,
    compare: bool = False,
    batch: bool = False,
    output_dir: str = "evaluation_reports",
    max_retries: int = 3,
    max_tokens: int = 1_000_000,
    verbose: bool = False,
) -> argparse.Namespace:
    """Build a minimal argparse.Namespace matching run.py's parse_args output."""
    return argparse.Namespace(
        planner_model=planner_model,
        reviewer_model=reviewer_model,
        persona=persona,
        compare=compare,
        batch=batch,
        output_dir=output_dir,
        max_retries=max_retries,
        max_tokens=max_tokens,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# run_single
# ---------------------------------------------------------------------------


class TestRunSingle:
    """W33 — Tests for the run_single() coroutine.

    run_single() creates a HarnessRunner, calls run_all (or run_all_batched),
    computes metrics, and writes plan_review_report.md to the output directory.
    """

    @pytest.mark.asyncio
    async def test_run_single_writes_report_to_output_dir(self, tmp_path: Path) -> None:
        """run_single writes plan_review_report.md into the output directory.

        WHY: The primary contract of run_single is producing the markdown
        artifact on disk. A bug that swaps output_dir or skips write_text
        would never be caught by a pure in-memory test.
        """
        from src.evaluation.run import run_single

        result = _make_persona_result("beginner_runner")
        mock_results = [result]
        mock_metrics = HarnessMetrics.from_results(
            mock_results,
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
        )

        args = _make_args(output_dir=str(tmp_path))

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_all = AsyncMock(return_value=mock_results)
            instance.compute_metrics = MagicMock(return_value=mock_metrics)

            await run_single(args)

        report_path = tmp_path / "plan_review_report.md"
        assert report_path.exists(), "plan_review_report.md must be written"
        content = report_path.read_text()
        assert "beginner_runner" in content

    @pytest.mark.asyncio
    async def test_run_single_calls_run_all_without_batch_flag(self, tmp_path: Path) -> None:
        """Without --batch, run_single calls run_all not run_all_batched.

        WHY: The batch flag must gate which method is called. A regression
        that always calls run_all_batched would fail in non-batch environments.
        """
        from src.evaluation.run import run_single

        result = _make_persona_result()
        mock_metrics = HarnessMetrics.from_results([result])
        args = _make_args(output_dir=str(tmp_path), batch=False)

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_all = AsyncMock(return_value=[result])
            instance.run_all_batched = AsyncMock(return_value=[result])
            instance.compute_metrics = MagicMock(return_value=mock_metrics)

            await run_single(args)

        instance.run_all.assert_called_once()
        instance.run_all_batched.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_single_calls_run_all_batched_with_batch_flag(self, tmp_path: Path) -> None:
        """With --batch, run_single calls run_all_batched.

        WHY: The batch path is the 50%-savings mode; it must be exercised
        separately so a routing bug doesn't silently fall back to sequential.
        """
        from src.evaluation.run import run_single

        result = _make_persona_result()
        mock_metrics = HarnessMetrics.from_results([result])
        args = _make_args(output_dir=str(tmp_path), batch=True)

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_all = AsyncMock(return_value=[result])
            instance.run_all_batched = AsyncMock(return_value=[result])
            instance.compute_metrics = MagicMock(return_value=mock_metrics)

            await run_single(args)

        instance.run_all_batched.assert_called_once()
        instance.run_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_single_passes_persona_filter(self, tmp_path: Path) -> None:
        """run_single passes persona_ids filter to run_all.

        WHY: The --persona CLI flag must propagate into the runner so partial
        runs (e.g. --persona beginner_runner) work correctly.
        """
        from src.evaluation.run import run_single

        result = _make_persona_result("advanced_marathoner")
        mock_metrics = HarnessMetrics.from_results([result])
        args = _make_args(
            output_dir=str(tmp_path),
            persona=["advanced_marathoner"],
        )

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_all = AsyncMock(return_value=[result])
            instance.compute_metrics = MagicMock(return_value=mock_metrics)

            await run_single(args)

        instance.run_all.assert_called_once_with(persona_ids=["advanced_marathoner"])

    @pytest.mark.asyncio
    async def test_run_single_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        """run_single creates a nested output dir if it does not exist.

        WHY: Users may pass --output-dir paths that don't yet exist. The
        mkdir(parents=True, exist_ok=True) call must be exercised.
        """
        from src.evaluation.run import run_single

        nested_dir = tmp_path / "nested" / "reports"
        assert not nested_dir.exists()

        result = _make_persona_result()
        mock_metrics = HarnessMetrics.from_results([result])
        args = _make_args(output_dir=str(nested_dir))

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_all = AsyncMock(return_value=[result])
            instance.compute_metrics = MagicMock(return_value=mock_metrics)

            await run_single(args)

        assert nested_dir.exists()
        assert (nested_dir / "plan_review_report.md").exists()

    @pytest.mark.asyncio
    async def test_run_single_constructs_runner_with_correct_params(self, tmp_path: Path) -> None:
        """HarnessRunner is constructed with values from args.

        WHY: If the constructor arguments are wired incorrectly (e.g. planner
        and reviewer swapped), we'd send Opus requests to a Sonnet endpoint.
        """
        from src.evaluation.run import run_single

        result = _make_persona_result()
        mock_metrics = HarnessMetrics.from_results([result])
        args = _make_args(
            planner_model="claude-sonnet-4-20250514",
            reviewer_model="claude-opus-4-20250514",
            max_retries=5,
            max_tokens=500_000,
            output_dir=str(tmp_path),
        )

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_all = AsyncMock(return_value=[result])
            instance.compute_metrics = MagicMock(return_value=mock_metrics)

            await run_single(args)

        MockRunner.assert_called_once()
        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["planner_model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["reviewer_model"] == "claude-opus-4-20250514"
        assert call_kwargs["max_retries"] == 5
        assert call_kwargs["max_total_tokens"] == 500_000


# ---------------------------------------------------------------------------
# run_comparison
# ---------------------------------------------------------------------------


class TestRunComparison:
    """W33 — Tests for the run_comparison() coroutine.

    run_comparison() runs each reviewer model, computes per-model metrics,
    writes a comparison_report.md, and one plan_review_{model}.md per model.
    """

    @pytest.mark.asyncio
    async def test_run_comparison_writes_comparison_report(self, tmp_path: Path) -> None:
        """run_comparison writes comparison_report.md to the output directory.

        WHY: This is the primary artifact of the Sonnet-vs-Opus benchmark.
        If the file is not produced, the entire comparison workflow is broken.
        """
        from src.evaluation.run import run_comparison

        result_opus = _make_persona_result("beginner_runner")
        result_sonnet = _make_persona_result("beginner_runner")
        comparison_data = {
            "claude-opus-4-20250514": [result_opus],
            "claude-sonnet-4-20250514": [result_sonnet],
        }

        args = _make_args(output_dir=str(tmp_path))

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_comparison = AsyncMock(return_value=comparison_data)

            await run_comparison(args)

        report_path = tmp_path / "comparison_report.md"
        assert report_path.exists(), "comparison_report.md must be written"
        content = report_path.read_text()
        assert "beginner_runner" in content

    @pytest.mark.asyncio
    async def test_run_comparison_writes_per_model_plan_reviews(self, tmp_path: Path) -> None:
        """run_comparison writes a plan_review_{model}.md for each reviewer model.

        WHY: The per-model plan review files allow reviewers to read each model's
        full generated plans. If the loop is broken, human review is impossible.
        """
        from src.evaluation.run import run_comparison

        result_opus = _make_persona_result("beginner_runner")
        result_sonnet = _make_persona_result("beginner_runner")
        comparison_data = {
            "claude-opus-4-20250514": [result_opus],
            "claude-sonnet-4-20250514": [result_sonnet],
        }

        args = _make_args(output_dir=str(tmp_path))

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_comparison = AsyncMock(return_value=comparison_data)

            await run_comparison(args)

        # The short name is extracted as model.split("-")[1]
        assert (tmp_path / "plan_review_opus.md").exists(), "opus plan review must be written"
        assert (tmp_path / "plan_review_sonnet.md").exists(), "sonnet plan review must be written"

    @pytest.mark.asyncio
    async def test_run_comparison_passes_persona_filter(self, tmp_path: Path) -> None:
        """run_comparison passes persona_ids from args to run_comparison().

        WHY: If the filter is dropped, the comparison always runs all 5 personas
        even when the user specified --persona to limit the scope.
        """
        from src.evaluation.run import run_comparison

        result = _make_persona_result("advanced_marathoner")
        comparison_data = {
            "claude-opus-4-20250514": [result],
            "claude-sonnet-4-20250514": [result],
        }
        args = _make_args(
            output_dir=str(tmp_path),
            persona=["advanced_marathoner"],
        )

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_comparison = AsyncMock(return_value=comparison_data)

            await run_comparison(args)

        instance.run_comparison.assert_called_once_with(
            persona_ids=["advanced_marathoner"],
        )

    @pytest.mark.asyncio
    async def test_run_comparison_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        """run_comparison creates the output directory if it does not exist."""
        from src.evaluation.run import run_comparison

        nested_dir = tmp_path / "compare_output"
        assert not nested_dir.exists()

        result = _make_persona_result("beginner_runner")
        comparison_data = {
            "claude-opus-4-20250514": [result],
            "claude-sonnet-4-20250514": [result],
        }
        args = _make_args(output_dir=str(nested_dir))

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_comparison = AsyncMock(return_value=comparison_data)

            await run_comparison(args)

        assert nested_dir.exists()
        assert (nested_dir / "comparison_report.md").exists()

    @pytest.mark.asyncio
    async def test_run_comparison_constructs_runner_with_correct_params(self, tmp_path: Path) -> None:
        """HarnessRunner is constructed with planner_model and retries from args.

        WHY: run_comparison does not set reviewer_model on the runner (it passes
        reviewer_models directly to run_comparison()). Verifying the other
        params are correctly forwarded prevents silent misconfiguration.
        """
        from src.evaluation.run import run_comparison

        result = _make_persona_result("beginner_runner")
        comparison_data = {
            "claude-opus-4-20250514": [result],
            "claude-sonnet-4-20250514": [result],
        }
        args = _make_args(
            planner_model="claude-sonnet-4-20250514",
            max_retries=7,
            max_tokens=750_000,
            output_dir=str(tmp_path),
        )

        with patch("src.evaluation.run.HarnessRunner") as MockRunner:
            instance = MockRunner.return_value
            instance.run_comparison = AsyncMock(return_value=comparison_data)

            await run_comparison(args)

        MockRunner.assert_called_once()
        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["planner_model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["max_retries"] == 7
        assert call_kwargs["max_total_tokens"] == 750_000
