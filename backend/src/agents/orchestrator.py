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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.agents.plan_postprocess import enrich_plan_with_tss
from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.reviewer import ReviewerAgent
from src.models.athlete import AthleteProfile
from src.models.decision_log import (
    DecisionLogEntry,
    ReviewerScores,
    ReviewOutcome,
)
from src.models.plan_change import PlanChangeType
from src.models.progress import ProgressEvent, ProgressEventType

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
        total_planner_input_tokens: Cumulative planner input tokens.
        total_planner_output_tokens: Cumulative planner output tokens.
        total_reviewer_input_tokens: Cumulative reviewer input tokens.
        total_reviewer_output_tokens: Cumulative reviewer output tokens.
        total_elapsed_seconds: Wall-clock time for the full orchestration.
        final_scores: Reviewer scores from the last review (None if never reviewed).
        warning: Set when max retries exhausted without approval.
        error: Set on fatal errors that prevented plan generation.
    """

    plan_text: str = ""
    approved: bool = False
    decision_log: list[DecisionLogEntry] = field(default_factory=list)
    total_iterations: int = 0
    total_planner_input_tokens: int = 0
    total_planner_output_tokens: int = 0
    total_reviewer_input_tokens: int = 0
    total_reviewer_output_tokens: int = 0
    total_elapsed_seconds: float = 0.0
    final_scores: ReviewerScores | None = None
    warning: str | None = None
    error: str | None = None
    athlete_cache_key: str = ""

    def summary(self) -> str:
        """Format key metrics as a human-readable summary.

        Returns:
            Multi-line string suitable for CLI or log output.
        """
        total_tokens = (
            self.total_planner_input_tokens + self.total_planner_output_tokens
            + self.total_reviewer_input_tokens + self.total_reviewer_output_tokens
        )
        lines = [
            f"Approved: {'YES' if self.approved else 'NO'}",
            f"Attempts: {len(self.decision_log)}",
            f"Total iterations: {self.total_iterations}",
            f"Total tokens: {total_tokens:,}",
            f"Elapsed: {self.total_elapsed_seconds:.1f}s",
        ]
        if self.final_scores:
            lines.append(f"Final scores: overall={self.final_scores.overall:.1f}")
        if self.warning:
            lines.append(f"Warning: {self.warning}")
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"OrchestrationResult(approved={self.approved}, "
            f"attempts={len(self.decision_log)}, "
            f"iterations={self.total_iterations}, "
            f"elapsed={self.total_elapsed_seconds:.1f}s)"
        )


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
        max_retries: Maximum number of planner-reviewer cycles. Defaults to 3.
        api_key: Anthropic API key (used only if planner/reviewer not provided).
        planner_model: Model for the planner (if constructing internally).
        reviewer_model: Model for the reviewer (if constructing internally).
        max_iterations: Per-agent iteration cap (forwarded to planner/reviewer
            constructors). Ignored if planner/reviewer are injected directly.
        max_total_tokens: Hard token budget across the entire orchestration.
            Aborts with a warning if cumulative tokens exceed this limit.
            Defaults to 1,000,000 (~$7.50 worst-case with Opus reviewer).

    Raises:
        ValueError: If max_retries < 1.
    """

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        reviewer: ReviewerAgent | None = None,
        max_retries: int = 4,
        api_key: str | None = None,
        planner_model: str = "claude-sonnet-4-20250514",
        reviewer_model: str = "claude-opus-4-20250514",
        max_iterations: int | None = None,
        max_total_tokens: int = 1_000_000,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")

        if max_iterations is not None and (planner is not None or reviewer is not None):
            logger.warning(
                "max_iterations=%d ignored because planner/reviewer were injected directly.",
                max_iterations,
            )

        resolved_reviewer_model = reviewer_model or "claude-opus-4-20250514"
        planner_kwargs: dict[str, Any] = {"api_key": api_key, "model": planner_model}
        reviewer_kwargs: dict[str, Any] = {"api_key": api_key, "model": resolved_reviewer_model}
        if max_iterations is not None:
            planner_kwargs["max_iterations"] = max_iterations
            reviewer_kwargs["max_iterations"] = max_iterations

        self._planner = planner or PlannerAgent(**planner_kwargs)
        self._reviewer = reviewer or ReviewerAgent(**reviewer_kwargs)
        self._max_retries = max_retries
        self._max_total_tokens = max_total_tokens
        self._on_progress = on_progress

    def _emit(self, event_type: str, message: str, **data: Any) -> None:
        """Emit a progress event if a callback is registered.

        Args:
            event_type: Event type string (must be a valid ProgressEventType value).
            message: Human-readable message.
            **data: Additional event data.

        Raises:
            ValueError: If event_type is not a valid ProgressEventType value.
        """
        if self._on_progress is not None:
            evt_type = ProgressEventType(event_type)
            self._on_progress(ProgressEvent(
                event_type=evt_type,
                message=message,
                data=data if data else {},
            ))

    @property
    def planner(self) -> PlannerAgent:
        """The planner agent."""
        return self._planner

    @property
    def reviewer(self) -> ReviewerAgent:
        """The reviewer agent."""
        return self._reviewer

    async def generate_plan(
        self,
        athlete: AthleteProfile,
        change_type: PlanChangeType = PlanChangeType.FULL,
        plan_start_date: date | None = None,
    ) -> OrchestrationResult:
        """Run the planner-reviewer orchestration loop.

        Routes based on change_type:
        - FULL: Full reviewer pass with all retries (default).
        - ADAPTATION: Reviewer with 1 retry (lightweight check).
        - TWEAK: Planner only, no reviewer, single pass.

        Does not raise; all errors are captured in OrchestrationResult.

        Args:
            athlete: The athlete profile to generate a plan for.
            change_type: Scope of the plan change. Controls reviewer
                involvement and retry count.

        Returns:
            OrchestrationResult with the best plan, approval status,
            and full decision log.
        """
        start_time = time.monotonic()
        result = OrchestrationResult()

        # Compute cache key for response deduplication
        result.athlete_cache_key = athlete.cache_key(
            salt=f"{self._planner.model}:{self._reviewer.model}:{change_type.value}"
        )

        # Route based on change type
        if change_type == PlanChangeType.TWEAK:
            effective_max_retries = 1
            skip_reviewer = True
        elif change_type == PlanChangeType.ADAPTATION:
            effective_max_retries = 1
            skip_reviewer = False
        else:  # FULL
            effective_max_retries = self._max_retries
            skip_reviewer = False

        logger.info(
            "Orchestration: change_type=%s, effective_max_retries=%d, skip_reviewer=%s",
            change_type.value, effective_max_retries, skip_reviewer,
        )

        last_valid_plan: str = ""
        last_reviewer_critique: str = ""
        last_reviewer_issues: list[str] = []

        for attempt in range(1, effective_max_retries + 1):
            total_tokens_so_far = (
                result.total_planner_input_tokens + result.total_planner_output_tokens
                + result.total_reviewer_input_tokens + result.total_reviewer_output_tokens
            )
            logger.info(
                "Orchestration attempt %d/%d, change_type=%s, tokens_so_far=%d",
                attempt, effective_max_retries, change_type.value, total_tokens_so_far,
            )

            try:
                # --- Step 1: Generate or revise plan ---
                self._emit(
                    "planner_started",
                    f"Planner starting attempt {attempt}/{effective_max_retries}",
                    attempt=attempt,
                    max_attempts=effective_max_retries,
                )
                if attempt == 1 or not last_valid_plan:
                    if attempt > 1:
                        logger.warning(
                            "Attempt %d: no valid prior plan to revise, regenerating from scratch. "
                            "Previous critique will not be forwarded.",
                            attempt,
                        )
                    planner_result = await self._planner.generate_plan(
                        athlete, plan_start_date=plan_start_date,
                    )
                else:
                    # We have reviewer feedback — revise
                    planner_result = await self._planner.revise_plan(
                        athlete,
                        last_valid_plan,
                        last_reviewer_critique,
                        last_reviewer_issues,
                    )

                result.total_planner_input_tokens += planner_result.total_input_tokens
                result.total_planner_output_tokens += planner_result.total_output_tokens
                result.total_iterations += planner_result.iterations

                self._emit(
                    "planner_complete",
                    f"Planner finished attempt {attempt} ({planner_result.iterations} iterations)",
                    attempt=attempt,
                    iterations=planner_result.iterations,
                    tokens=planner_result.total_input_tokens + planner_result.total_output_tokens,
                )

                # --- Token budget check ---
                total_tokens = (
                    result.total_planner_input_tokens + result.total_planner_output_tokens
                    + result.total_reviewer_input_tokens + result.total_reviewer_output_tokens
                )
                logger.info(
                    "Token usage after planner: %d/%d (%.1f%%)",
                    total_tokens, self._max_total_tokens,
                    total_tokens / self._max_total_tokens * 100,
                )
                if total_tokens > self._max_total_tokens:
                    self._emit(
                        "token_budget",
                        f"Token budget exceeded ({total_tokens:,}/{self._max_total_tokens:,})",
                        total_tokens=total_tokens,
                        budget=self._max_total_tokens,
                    )
                    logger.warning(
                        "Token budget exceeded (%d > %d). Aborting orchestration.",
                        total_tokens, self._max_total_tokens,
                    )
                    result.plan_text = last_valid_plan
                    result.warning = (
                        f"Token budget exceeded ({total_tokens:,} > "
                        f"{self._max_total_tokens:,}). Returning best plan so far."
                    )
                    result.total_elapsed_seconds = time.monotonic() - start_time
                    return result

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
                    self._emit(
                        "validation_result",
                        f"Validation failed: {len(planner_result.validation.issues)} issues",
                        passed=False,
                        issues=planner_result.validation.issues,
                    )

                    # Use whatever critique we have for next revision
                    last_reviewer_critique = planner_result.error or "Phase 2 validation failed."
                    last_reviewer_issues = planner_result.validation.issues
                    if planner_result.plan_text:
                        last_valid_plan = planner_result.plan_text
                    continue

                # Plan passed structural validation — enrich with computed TSS
                enriched_text = enrich_plan_with_tss(planner_result.plan_text)
                planner_result = PlannerResult(
                    plan_text=enriched_text,
                    tool_calls=planner_result.tool_calls,
                    iterations=planner_result.iterations,
                    total_input_tokens=planner_result.total_input_tokens,
                    total_output_tokens=planner_result.total_output_tokens,
                    validation=planner_result.validation,
                    error=planner_result.error,
                )
                last_valid_plan = planner_result.plan_text

                # --- Step 3: Reviewer evaluates (or skip) ---
                if skip_reviewer:
                    logger.info(
                        "Reviewer skipped (change_type=%s). Auto-approving.",
                        change_type.value,
                    )
                    entry = DecisionLogEntry(
                        iteration=attempt,
                        outcome=ReviewOutcome.APPROVED,
                        critique=f"Auto-approved (change_type={change_type.value}, reviewer skipped).",
                        planner_input_tokens=planner_result.total_input_tokens,
                        planner_output_tokens=planner_result.total_output_tokens,
                        planner_tool_calls=len(planner_result.tool_calls),
                    )
                    result.decision_log.append(entry)
                    result.plan_text = planner_result.plan_text
                    result.approved = True
                    result.total_elapsed_seconds = time.monotonic() - start_time
                    return result

                self._emit(
                    "reviewer_started",
                    f"Reviewer evaluating plan (attempt {attempt})",
                    attempt=attempt,
                )
                reviewer_result = await self._reviewer.review_plan(
                    athlete,
                    planner_result.plan_text,
                    planner_result.tool_calls,
                )

                result.total_reviewer_input_tokens += reviewer_result.total_input_tokens
                result.total_reviewer_output_tokens += reviewer_result.total_output_tokens
                result.total_iterations += reviewer_result.iterations

                scores_data = (
                    reviewer_result.scores.model_dump()
                    if reviewer_result.scores else None
                )
                self._emit(
                    "reviewer_complete",
                    f"Reviewer finished: {'approved' if reviewer_result.approved else 'rejected'}",
                    attempt=attempt,
                    approved=reviewer_result.approved,
                    scores=scores_data,
                    critique=reviewer_result.critique[:200] if reviewer_result.critique else "",
                )

                # --- Token budget re-check after reviewer ---
                total_tokens = (
                    result.total_planner_input_tokens + result.total_planner_output_tokens
                    + result.total_reviewer_input_tokens + result.total_reviewer_output_tokens
                )
                logger.info(
                    "Token usage after reviewer: %d/%d (%.1f%%)",
                    total_tokens, self._max_total_tokens,
                    total_tokens / self._max_total_tokens * 100,
                )
                if total_tokens > self._max_total_tokens:
                    logger.warning(
                        "Token budget exceeded after reviewer (%d > %d). Aborting.",
                        total_tokens, self._max_total_tokens,
                    )
                    result.plan_text = last_valid_plan
                    result.warning = (
                        f"Token budget exceeded ({total_tokens:,} > "
                        f"{self._max_total_tokens:,}). Returning best plan so far."
                    )
                    result.total_elapsed_seconds = time.monotonic() - start_time
                    return result

                # --- Step 4: Log the outcome ---
                # Server-side guard: override LLM approval if scores fail threshold
                approved = reviewer_result.approved
                if approved and reviewer_result.scores and not reviewer_result.scores.all_pass:
                    logger.warning(
                        "Reviewer approved but scores fail threshold (overall=%.1f). "
                        "Overriding to rejected.",
                        reviewer_result.scores.overall,
                    )
                    approved = False

                if reviewer_result.error and not reviewer_result.scores:
                    outcome = ReviewOutcome.ERROR
                elif approved:
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
                if approved:
                    overall_score = (
                        reviewer_result.scores.overall
                        if reviewer_result.scores
                        else None
                    )
                    logger.info(
                        "Plan approved on attempt %d, overall_score=%s, total_tokens=%d",
                        attempt, overall_score, total_tokens,
                    )
                    result.plan_text = planner_result.plan_text
                    result.approved = True
                    result.total_elapsed_seconds = time.monotonic() - start_time
                    return result

                # Rejected or error — prepare for next revision
                if attempt < effective_max_retries:
                    self._emit(
                        "retry",
                        f"Plan rejected, retrying ({attempt}/{effective_max_retries})",
                        attempt=attempt,
                        max_attempts=effective_max_retries,
                        issues=reviewer_result.issues[:5],
                    )
                last_reviewer_critique = reviewer_result.critique or reviewer_result.error or ""
                last_reviewer_issues = reviewer_result.issues

            except Exception as e:
                logger.error(
                    "Unexpected error on attempt %d: %s", attempt, e, exc_info=True,
                )
                entry = DecisionLogEntry(
                    iteration=attempt,
                    outcome=ReviewOutcome.ERROR,
                    critique=f"Unexpected error: {type(e).__name__}: {e}",
                )
                result.decision_log.append(entry)
                result.error = f"Unexpected error on attempt {attempt}: {type(e).__name__}: {e}"
                result.plan_text = last_valid_plan
                result.total_elapsed_seconds = time.monotonic() - start_time
                return result

        # --- Max retries exhausted ---
        total_tokens = (
            result.total_planner_input_tokens + result.total_planner_output_tokens
            + result.total_reviewer_input_tokens + result.total_reviewer_output_tokens
        )
        best_score = result.final_scores.overall if result.final_scores else None
        logger.warning(
            "Max retries (%d) exhausted without approval, change_type=%s, "
            "total_tokens=%d, best_score=%s",
            effective_max_retries, change_type.value, total_tokens, best_score,
        )
        result.plan_text = last_valid_plan
        result.warning = (
            f"Plan was not approved after {effective_max_retries} "
            f"{'attempt' if effective_max_retries == 1 else 'attempts'} "
            f"(change_type={change_type.value}). Returning the last generated plan."
        )
        result.total_elapsed_seconds = time.monotonic() - start_time
        return result
