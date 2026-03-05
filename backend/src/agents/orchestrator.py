"""Orchestrator — drives the planner-reviewer retry loop.

Coordinates the PlannerAgent and ReviewerAgent through an iterative cycle:
1. Planner generates (or revises) a plan.
2. Phase 2 validation pre-filters structural issues.
3. Reviewer scores the plan across 4 dimensions.
4. If rejected, planner revises based on critique.
5. Repeat until approved or max retries exhausted.

Usage:
    orchestrator = Orchestrator(api_key="sk-...")
    result = await orchestrator.generate_plan(athlete)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.reviewer import ReviewerAgent, ReviewerResult
from src.models.athlete import AthleteProfile
from src.models.decision_log import (
    DecisionLogEntry,
    ReviewerScores,
    ReviewOutcome,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestrationResult:
    """Result of the full planner-reviewer orchestration cycle.

    Attributes:
        plan_text: The final plan text (best available).
        approved: Whether the plan was approved by the reviewer.
        decision_log: Per-iteration records of outcomes and scores.
        total_iterations: Total planner+reviewer iterations across all retries.
        total_planner_tokens: Cumulative planner token usage.
        total_reviewer_tokens: Cumulative reviewer token usage.
        total_elapsed_seconds: Wall-clock time for the full orchestration.
        final_scores: Reviewer scores from the last review (None if never reviewed).
        warning: Set when max retries exhausted without approval.
        error: Set on fatal errors that prevented plan generation.
    """

    plan_text: str = ""
    approved: bool = False
    decision_log: list[DecisionLogEntry] = field(default_factory=list)
    total_iterations: int = 0
    total_planner_tokens: int = 0
    total_reviewer_tokens: int = 0
    total_elapsed_seconds: float = 0.0
    final_scores: ReviewerScores | None = None
    warning: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Drives the planner-reviewer negotiation loop.

    The orchestrator coordinates plan generation and review through an
    iterative cycle, logging each iteration's outcome for analysis.

    Args:
        planner: PlannerAgent instance (injected for testability).
        reviewer: ReviewerAgent instance (injected for testability).
        max_retries: Maximum number of planner-reviewer cycles. Defaults to 5.
        api_key: Anthropic API key (used only if planner/reviewer not provided).
        planner_model: Model for the planner (if constructing internally).
        reviewer_model: Model for the reviewer (if constructing internally).
    """

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        reviewer: ReviewerAgent | None = None,
        max_retries: int = 5,
        api_key: str | None = None,
        planner_model: str = "claude-sonnet-4-20250514",
        reviewer_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._planner = planner or PlannerAgent(api_key=api_key, model=planner_model)
        self._reviewer = reviewer or ReviewerAgent(api_key=api_key, model=reviewer_model)
        self._max_retries = max_retries

    @property
    def planner(self) -> PlannerAgent:
        """The planner agent."""
        return self._planner

    @property
    def reviewer(self) -> ReviewerAgent:
        """The reviewer agent."""
        return self._reviewer

    async def generate_plan(self, athlete: AthleteProfile) -> OrchestrationResult:
        """Run the full planner-reviewer orchestration loop.

        Args:
            athlete: The athlete profile to generate a plan for.

        Returns:
            OrchestrationResult with the best plan, approval status,
            and full decision log.
        """
        start_time = time.monotonic()
        result = OrchestrationResult()
        last_valid_plan: str = ""
        last_planner_result: PlannerResult | None = None

        for attempt in range(1, self._max_retries + 1):
            logger.info("Orchestration attempt %d/%d", attempt, self._max_retries)

            # --- Step 1: Generate or revise plan ---
            if attempt == 1:
                planner_result = await self._planner.generate_plan(athlete)
            else:
                # We have reviewer feedback — revise
                planner_result = await self._planner.revise_plan(
                    athlete,
                    last_valid_plan,
                    last_reviewer_critique,
                    last_reviewer_issues,
                )

            result.total_planner_tokens += (
                planner_result.total_input_tokens + planner_result.total_output_tokens
            )
            result.total_iterations += planner_result.iterations

            # --- Step 2: Pre-filter with Phase 2 validation ---
            if planner_result.validation and not planner_result.validation.passed:
                logger.warning(
                    "Attempt %d: Phase 2 validation failed, skipping reviewer. Issues: %s",
                    attempt,
                    planner_result.validation.issues,
                )
                entry = DecisionLogEntry(
                    iteration=attempt,
                    outcome=ReviewOutcome.ERROR,
                    critique=planner_result.error or "Phase 2 validation failed.",
                    issues=planner_result.validation.issues,
                    planner_input_tokens=planner_result.total_input_tokens,
                    planner_output_tokens=planner_result.total_output_tokens,
                    planner_tool_calls=len(planner_result.tool_calls),
                )
                result.decision_log.append(entry)

                # Use whatever critique we have for next revision
                last_reviewer_critique = planner_result.error or "Phase 2 validation failed."
                last_reviewer_issues = planner_result.validation.issues
                if planner_result.plan_text:
                    last_valid_plan = planner_result.plan_text
                last_planner_result = planner_result
                continue

            # Plan passed structural validation
            last_valid_plan = planner_result.plan_text
            last_planner_result = planner_result

            # --- Step 3: Reviewer evaluates ---
            reviewer_result = await self._reviewer.review_plan(
                athlete,
                planner_result.plan_text,
                planner_result.tool_calls,
            )

            result.total_reviewer_tokens += (
                reviewer_result.total_input_tokens + reviewer_result.total_output_tokens
            )
            result.total_iterations += reviewer_result.iterations

            # --- Step 4: Log the outcome ---
            if reviewer_result.error and not reviewer_result.scores:
                outcome = ReviewOutcome.ERROR
            elif reviewer_result.approved:
                outcome = ReviewOutcome.APPROVED
            else:
                outcome = ReviewOutcome.REJECTED

            entry = DecisionLogEntry(
                iteration=attempt,
                outcome=outcome,
                scores=reviewer_result.scores,
                critique=reviewer_result.critique,
                issues=reviewer_result.issues,
                planner_input_tokens=planner_result.total_input_tokens,
                planner_output_tokens=planner_result.total_output_tokens,
                reviewer_input_tokens=reviewer_result.total_input_tokens,
                reviewer_output_tokens=reviewer_result.total_output_tokens,
                planner_tool_calls=len(planner_result.tool_calls),
                reviewer_tool_calls=len(reviewer_result.tool_calls),
            )
            result.decision_log.append(entry)
            result.final_scores = reviewer_result.scores

            # --- Step 5: Check outcome ---
            if reviewer_result.approved:
                logger.info("Plan approved on attempt %d", attempt)
                result.plan_text = planner_result.plan_text
                result.approved = True
                result.total_elapsed_seconds = time.monotonic() - start_time
                return result

            # Rejected or error — prepare for next revision
            last_reviewer_critique = reviewer_result.critique or reviewer_result.error or ""
            last_reviewer_issues = reviewer_result.issues

        # --- Max retries exhausted ---
        logger.warning(
            "Max retries (%d) exhausted without approval.", self._max_retries,
        )
        result.plan_text = last_valid_plan
        result.warning = (
            f"Plan was not approved after {self._max_retries} attempts. "
            f"Returning the last generated plan."
        )
        result.total_elapsed_seconds = time.monotonic() - start_time
        return result
