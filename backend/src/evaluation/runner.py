"""Harness runner — executes all personas through the orchestrator.

Runs each synthetic athlete through the full planner-reviewer pipeline
and collects PersonaResult instances for analysis.

Usage:
    runner = HarnessRunner(api_key="sk-...")
    results = await runner.run_all()
    metrics = HarnessMetrics.from_results(results)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from src.agents.batch import BatchCoordinator
from src.agents.orchestrator import Orchestrator, OrchestrationResult
from src.agents.planner import PlannerAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.transport import MessageTransport
from src.evaluation.personas import (
    ALL_PERSONAS,
    EvaluationPersona,
    ExpectedBehavior,
    get_persona,
)
from src.evaluation.results import HarnessMetrics, PersonaResult
from src.models.plan_change import PlanChangeType

logger = logging.getLogger(__name__)

# Timeout for the entire batched run (2 hours default)
_BATCH_TIMEOUT_SECONDS = 7200.0


def check_constraint_violations(
    plan_text: str,
    expected: ExpectedBehavior,
    safety_score: float | None = None,
) -> list[str]:
    """Check a plan against expected behavior constraints.

    Performs text-based checks on the generated plan to verify it meets
    the persona's expected constraints. This is a post-hoc analysis that
    populates the constraint_violations field on PersonaResult.

    Args:
        plan_text: The generated plan text.
        expected: The persona's expected behavior constraints.
        safety_score: Reviewer's safety score (None if not reviewed).

    Returns:
        List of violation descriptions. Empty if all constraints pass.
    """
    violations: list[str] = []
    text_lower = plan_text.lower()

    for phrase in expected.must_include:
        if phrase.lower() not in text_lower:
            violations.append(f"Missing required phrase: '{phrase}'")

    for phrase in expected.must_not_include:
        if phrase.lower() in text_lower:
            violations.append(f"Contains prohibited phrase: '{phrase}'")

    if safety_score is not None and safety_score < expected.min_safety_score:
        violations.append(
            f"Safety score {safety_score:.0f} below minimum {expected.min_safety_score:.0f}"
        )

    # Check for ACWR values in plan text that exceed expected max
    if hasattr(expected, "max_acwr"):
        acwr_pattern = re.compile(r"ACWR\s*[:=]?\s*(\d+\.?\d*)", re.IGNORECASE)
        for match in acwr_pattern.finditer(plan_text):
            acwr_value = float(match.group(1))
            if acwr_value > expected.max_acwr:
                violations.append(
                    f"ACWR {acwr_value:.2f} exceeds maximum {expected.max_acwr:.2f}"
                )

    return violations


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

    def _result_from_orchestration(
        self,
        persona_id: str,
        orch_result: OrchestrationResult,
        elapsed: float,
    ) -> PersonaResult:
        """Build a PersonaResult from an OrchestrationResult.

        Args:
            persona_id: The persona that was evaluated.
            orch_result: Result from the orchestrator.
            elapsed: Wall-clock seconds for this persona.

        Returns:
            Populated PersonaResult with constraint violations checked.
        """
        # Check constraint violations against persona's expected behavior
        violations: list[str] = []
        try:
            persona = get_persona(persona_id)
            safety_score = (
                orch_result.final_scores.safety
                if orch_result.final_scores is not None
                else None
            )
            violations = check_constraint_violations(
                orch_result.plan_text,
                persona.expected_behavior,
                safety_score=safety_score,
            )
        except KeyError:
            logger.warning(
                "Could not find persona '%s' for constraint checking — "
                "skipping violation analysis",
                persona_id,
            )

        return PersonaResult(
            persona_id=persona_id,
            plan_text=orch_result.plan_text,
            approved=orch_result.approved,
            retry_count=len(orch_result.decision_log),
            total_iterations=orch_result.total_iterations,
            final_scores=orch_result.final_scores,
            decision_log=orch_result.decision_log,
            planner_input_tokens=orch_result.total_planner_input_tokens,
            planner_output_tokens=orch_result.total_planner_output_tokens,
            reviewer_input_tokens=orch_result.total_reviewer_input_tokens,
            reviewer_output_tokens=orch_result.total_reviewer_output_tokens,
            elapsed_seconds=elapsed,
            constraint_violations=violations,
            athlete_cache_key=orch_result.athlete_cache_key,
            warning=orch_result.warning,
            error=orch_result.error,
            planner_model=self._planner_model,
            reviewer_model=self._reviewer_model,
        )

    def _error_result(
        self,
        persona_id: str,
        error: Exception,
        elapsed: float,
    ) -> PersonaResult:
        """Build an error PersonaResult.

        Args:
            persona_id: The persona that failed.
            error: The exception that occurred.
            elapsed: Wall-clock seconds before failure.

        Returns:
            PersonaResult with error details.
        """
        return PersonaResult(
            persona_id=persona_id,
            error=f"{type(error).__name__}: {error}",
            elapsed_seconds=elapsed,
            planner_model=self._planner_model,
            reviewer_model=self._reviewer_model,
        )

    def _build_orchestrator_with_transports(
        self,
        planner_transport: MessageTransport,
        reviewer_transport: MessageTransport,
    ) -> Orchestrator:
        """Construct an Orchestrator with explicit transports.

        Args:
            planner_transport: Transport for the planner agent.
            reviewer_transport: Transport for the reviewer agent.

        Returns:
            Configured Orchestrator instance.
        """
        planner = PlannerAgent(model=self._planner_model, transport=planner_transport)
        reviewer = ReviewerAgent(model=self._reviewer_model, transport=reviewer_transport)

        return Orchestrator(
            planner=planner,
            reviewer=reviewer,
            max_retries=self._max_retries,
            max_total_tokens=self._max_total_tokens,
        )

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

        Raises:
            KeyError: If the persona ID is not registered (with a clear message).
        """
        # Validate persona is registered before spending API tokens
        try:
            get_persona(persona.persona_id)
        except KeyError:
            raise KeyError(
                f"Unknown persona '{persona.persona_id}'. "
                f"Registered personas: {[p.persona_id for p in ALL_PERSONAS]}"
            ) from None

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
            return self._error_result(persona.persona_id, e, elapsed)

        elapsed = time.monotonic() - start
        return self._result_from_orchestration(persona.persona_id, orch_result, elapsed)

    async def run_all(
        self,
        persona_ids: list[str] | None = None,
    ) -> list[PersonaResult]:
        """Run all (or selected) personas sequentially.

        Args:
            persona_ids: Optional list of persona IDs to run. If None, runs all personas.

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
            self._log_result(result)

        return results

    async def run_all_batched(
        self,
        persona_ids: list[str] | None = None,
        poll_interval: float = 5.0,
    ) -> list[PersonaResult]:
        """Run all personas concurrently using batch API for 50% cost savings.

        Creates a ``BatchCoordinator`` that collects API calls from all persona
        runs and submits them as batch requests. All personas run concurrently
        via ``asyncio.gather``, with each round of API calls batched together.

        Note: Batch mode requires ``change_type`` to be FULL or ADAPTATION.
        TWEAK mode skips the reviewer, which would deadlock the batch barrier.

        Args:
            persona_ids: Optional list of persona IDs to run. If None, runs all personas.
            poll_interval: Seconds between batch status polls.

        Returns:
            List of PersonaResult, one per persona (order matches input).

        Raises:
            ValueError: If api_key is not set or change_type is TWEAK.
        """
        if not self._api_key:
            raise ValueError("api_key is required for batch mode (no mock transport)")

        if self._change_type == PlanChangeType.TWEAK:
            raise ValueError(
                "Batch mode is incompatible with TWEAK change_type "
                "(reviewer transport would never enqueue, causing deadlock)"
            )

        if persona_ids:
            personas = [get_persona(pid) for pid in persona_ids]
        else:
            personas = list(ALL_PERSONAS)

        coordinator = BatchCoordinator(
            api_key=self._api_key,
            poll_interval_seconds=poll_interval,
        )

        async def _run_persona_batched(
            persona: EvaluationPersona,
        ) -> PersonaResult:
            """Run a single persona with batch transports."""
            pid = persona.persona_id
            planner_t = coordinator.register_transport(f"{pid}:planner")
            reviewer_t = coordinator.register_transport(f"{pid}:reviewer")
            orchestrator = self._build_orchestrator_with_transports(planner_t, reviewer_t)

            start = time.monotonic()
            try:
                orch_result = await orchestrator.generate_plan(
                    persona.profile,
                    change_type=self._change_type,
                )
            except Exception as e:
                elapsed = time.monotonic() - start
                logger.error("Persona %s failed: %s", pid, e, exc_info=True)
                return self._error_result(pid, e, elapsed)
            finally:
                coordinator.deregister_transport(f"{pid}:planner")
                coordinator.deregister_transport(f"{pid}:reviewer")

            elapsed = time.monotonic() - start
            return self._result_from_orchestration(pid, orch_result, elapsed)

        # Start coordinator and run all personas concurrently with timeout
        await coordinator.start()
        try:
            tasks = [_run_persona_batched(p) for p in personas]
            results = await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=_BATCH_TIMEOUT_SECONDS,
            )
        finally:
            await coordinator.stop()

        # Verify results list integrity — every persona should have a result
        results_list = list(results)
        if len(results_list) != len(personas):
            logger.error(
                "Results count mismatch: expected %d, got %d",
                len(personas), len(results_list),
            )

        for result in results_list:
            self._log_result(result)

        return results_list

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

    @staticmethod
    def _log_result(result: PersonaResult) -> None:
        """Log a persona result summary.

        Args:
            result: The PersonaResult to log.
        """
        logger.info(
            "Persona %s: approved=%s, retries=%d, tokens=%d, cost=$%.4f, "
            "time=%.1fs, constraint_violations=%d, "
            "planner_model=%s, reviewer_model=%s",
            result.persona_id,
            result.approved,
            result.retry_count,
            result.total_tokens,
            result.estimated_cost_usd,
            result.elapsed_seconds,
            len(result.constraint_violations),
            result.planner_model,
            result.reviewer_model,
        )
