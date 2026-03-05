"""Harness runner — executes all personas through the orchestrator.

Runs each synthetic athlete through the full planner-reviewer pipeline
and collects PersonaResult instances for analysis.

Usage:
    runner = HarnessRunner(api_key="sk-...")
    results = await runner.run_all()
    metrics = HarnessMetrics.from_results(results)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.agents.orchestrator import Orchestrator
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.transport import MessageTransport
from src.evaluation.personas import ALL_PERSONAS, EvaluationPersona, get_persona
from src.evaluation.results import HarnessMetrics, PersonaResult
from src.models.plan_change import PlanChangeType

logger = logging.getLogger(__name__)


class HarnessRunner:
    """Runs evaluation personas through the orchestrator pipeline.

    Args:
        api_key: Anthropic API key.
        planner_model: Model ID for the planner agent.
        reviewer_model: Model ID for the reviewer agent.
        change_type: PlanChangeType routing for all runs.
        max_retries: Orchestrator retry cap.
        max_total_tokens: Per-persona token budget.
        transport: Optional MessageTransport (for mock testing).
    """

    def __init__(
        self,
        api_key: str | None = None,
        planner_model: str = "claude-sonnet-4-20250514",
        reviewer_model: str = "claude-opus-4-20250514",
        change_type: PlanChangeType = PlanChangeType.FULL,
        max_retries: int = 3,
        max_total_tokens: int = 1_000_000,
        transport: MessageTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._planner_model = planner_model
        self._reviewer_model = reviewer_model
        self._change_type = change_type
        self._max_retries = max_retries
        self._max_total_tokens = max_total_tokens
        self._transport = transport

    def _build_orchestrator(self) -> Orchestrator:
        """Construct an Orchestrator with the configured models and transport.

        Returns:
            Configured Orchestrator instance.
        """
        planner_kwargs: dict[str, Any] = {"model": self._planner_model}
        reviewer_kwargs: dict[str, Any] = {"model": self._reviewer_model}

        if self._transport is not None:
            planner_kwargs["transport"] = self._transport
            reviewer_kwargs["transport"] = self._transport
        else:
            planner_kwargs["api_key"] = self._api_key
            reviewer_kwargs["api_key"] = self._api_key

        planner = PlannerAgent(**planner_kwargs)
        reviewer = ReviewerAgent(**reviewer_kwargs)

        return Orchestrator(
            planner=planner,
            reviewer=reviewer,
            max_retries=self._max_retries,
            max_total_tokens=self._max_total_tokens,
        )

    async def run_persona(self, persona: EvaluationPersona) -> PersonaResult:
        """Run a single persona through the orchestrator.

        Args:
            persona: The evaluation persona to run.

        Returns:
            PersonaResult with plan, scores, tokens, and timing.
        """
        logger.info("Running persona: %s", persona.persona_id)
        orchestrator = self._build_orchestrator()
        start = time.monotonic()

        try:
            orch_result = await orchestrator.generate_plan(
                persona.profile,
                change_type=self._change_type,
            )
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(
                "Persona %s failed: %s", persona.persona_id, e, exc_info=True,
            )
            return PersonaResult(
                persona_id=persona.persona_id,
                error=f"{type(e).__name__}: {e}",
                elapsed_seconds=elapsed,
                planner_model=self._planner_model,
                reviewer_model=self._reviewer_model,
            )

        elapsed = time.monotonic() - start

        return PersonaResult(
            persona_id=persona.persona_id,
            plan_text=orch_result.plan_text,
            approved=orch_result.approved,
            retry_count=len(orch_result.decision_log),  # review cycles (includes initial)
            total_iterations=orch_result.total_iterations,
            final_scores=orch_result.final_scores,
            decision_log=orch_result.decision_log,
            planner_input_tokens=orch_result.total_planner_input_tokens,
            planner_output_tokens=orch_result.total_planner_output_tokens,
            reviewer_input_tokens=orch_result.total_reviewer_input_tokens,
            reviewer_output_tokens=orch_result.total_reviewer_output_tokens,
            elapsed_seconds=elapsed,
            athlete_cache_key=orch_result.athlete_cache_key,
            warning=orch_result.warning,
            error=orch_result.error,
            planner_model=self._planner_model,
            reviewer_model=self._reviewer_model,
        )

    async def run_all(
        self,
        persona_ids: list[str] | None = None,
    ) -> list[PersonaResult]:
        """Run all (or selected) personas sequentially.

        Args:
            persona_ids: Optional list of persona IDs to run. If None, runs all 5.

        Returns:
            List of PersonaResult, one per persona.
        """
        if persona_ids:
            personas = [get_persona(pid) for pid in persona_ids]
        else:
            personas = list(ALL_PERSONAS)

        results: list[PersonaResult] = []
        for persona in personas:
            result = await self.run_persona(persona)
            results.append(result)
            logger.info(
                "Persona %s: approved=%s, retries=%d, tokens=%d, cost=$%.4f, time=%.1fs",
                result.persona_id,
                result.approved,
                result.retry_count,
                result.total_tokens,
                result.estimated_cost_usd,
                result.elapsed_seconds,
            )

        return results

    async def run_comparison(
        self,
        reviewer_models: list[str] | None = None,
        persona_ids: list[str] | None = None,
    ) -> dict[str, list[PersonaResult]]:
        """Run the harness with multiple reviewer models for comparison.

        This is the key Sonnet-vs-Opus comparison. Runs all personas once
        per reviewer model and returns results grouped by model.

        Args:
            reviewer_models: List of model IDs to compare. Defaults to
                Opus and Sonnet.
            persona_ids: Optional subset of persona IDs.

        Returns:
            Dict mapping reviewer model ID to list of PersonaResult.
        """
        if reviewer_models is None:
            reviewer_models = [
                "claude-opus-4-20250514",
                "claude-sonnet-4-20250514",
            ]

        all_results: dict[str, list[PersonaResult]] = {}

        for model in reviewer_models:
            logger.info("=== Comparison run: reviewer=%s ===", model)
            model_runner = HarnessRunner(
                api_key=self._api_key,
                planner_model=self._planner_model,
                reviewer_model=model,
                change_type=self._change_type,
                max_retries=self._max_retries,
                max_total_tokens=self._max_total_tokens,
                transport=self._transport,
            )
            results = await model_runner.run_all(persona_ids=persona_ids)
            all_results[model] = results

        return all_results

    def compute_metrics(
        self,
        results: list[PersonaResult],
        total_elapsed_seconds: float = 0.0,
    ) -> HarnessMetrics:
        """Compute aggregate metrics from a set of results.

        Args:
            results: List of PersonaResult from a harness run.
            total_elapsed_seconds: Wall-clock time for the run.

        Returns:
            Aggregated HarnessMetrics.
        """
        return HarnessMetrics.from_results(
            results,
            planner_model=self._planner_model,
            reviewer_model=self._reviewer_model,
            total_elapsed_seconds=total_elapsed_seconds,
        )
