"""Decision log models for the multi-agent orchestration loop.

Tracks per-iteration outcomes, reviewer scores, and convergence data
across the planner-reviewer retry cycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


REVIEW_PASS_THRESHOLD: int = 70
"""Minimum score (0-100) required for each review dimension to pass.

Also referenced in REVIEWER_SYSTEM_PROMPT (src/agents/prompts.py) and
ReviewerAgent._build_review_message — keep in sync.
"""


class ReviewDimension(str, Enum):
    """Dimensions evaluated by the reviewer agent."""

    SAFETY = "safety"
    PROGRESSION = "progression"
    SPECIFICITY = "specificity"
    FEASIBILITY = "feasibility"


class ReviewerScores(BaseModel):
    """Scores across all four review dimensions (0-100 each).

    Safety is weighted 2x in the overall score because unsafe plans
    must never reach athletes.

    Attributes:
        safety: Rest days, 80/20 intensity, ACWR limits, injury awareness.
        progression: Weekly load increases, step-back weeks.
        specificity: Workouts match goal event and training phase.
        feasibility: Duration/intensity realistic for athlete level.
    """

    safety: int = Field(ge=0, le=100, description="Safety score (2x weight)")
    progression: int = Field(ge=0, le=100, description="Progression score")
    specificity: int = Field(ge=0, le=100, description="Specificity score")
    feasibility: int = Field(ge=0, le=100, description="Feasibility score")

    @property
    def overall(self) -> float:
        """Weighted average: safety counts 2x, others 1x each.

        Returns:
            Weighted average score (0-100).
        """
        return (self.safety * 2 + self.progression + self.specificity + self.feasibility) / 5

    @property
    def all_pass(self) -> bool:
        """Whether every dimension meets the 70-point threshold.

        Returns:
            True if all four scores are >= 70.
        """
        return all(
            score >= REVIEW_PASS_THRESHOLD
            for score in (self.safety, self.progression, self.specificity, self.feasibility)
        )


class ReviewOutcome(str, Enum):
    """Possible outcomes of a single review iteration."""

    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class DecisionLogEntry(BaseModel):
    """A single iteration's record in the orchestration decision log.

    Attributes:
        iteration: 1-based iteration number.
        timestamp: When this iteration completed.
        outcome: Whether the plan was approved, rejected, or errored.
        scores: Reviewer dimension scores (None on error or validation failure).
        critique: Reviewer's textual critique (empty on approval/error).
        issues: Specific issues identified by the reviewer.
        planner_input_tokens: Planner token usage for this iteration.
        planner_output_tokens: Planner token usage for this iteration.
        reviewer_input_tokens: Reviewer token usage (0 if reviewer was skipped).
        reviewer_output_tokens: Reviewer token usage (0 if reviewer was skipped).
        planner_tool_calls: Number of tool calls the planner made.
        reviewer_tool_calls: Number of tool calls the reviewer made.
    """

    iteration: int = Field(ge=1, description="1-based iteration number")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    outcome: ReviewOutcome
    scores: ReviewerScores | None = None
    critique: str = ""
    issues: list[str] = Field(default_factory=list)
    planner_input_tokens: int = Field(default=0, ge=0)
    planner_output_tokens: int = Field(default=0, ge=0)
    reviewer_input_tokens: int = Field(default=0, ge=0)
    reviewer_output_tokens: int = Field(default=0, ge=0)
    planner_tool_calls: int = Field(default=0, ge=0)
    reviewer_tool_calls: int = Field(default=0, ge=0)
