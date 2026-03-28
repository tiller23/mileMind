"""Evaluation result models for harness benchmarking.

Captures per-persona outcomes and aggregate metrics across all personas.
These models are the output of a harness run and feed into report generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.models.decision_log import DecisionLogEntry, ReviewerScores

# ---------------------------------------------------------------------------
# Model pricing (USD per million tokens, as of 2026-03)
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # model_id_prefix: (input_rate_per_M, output_rate_per_M)
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "claude-haiku": (0.80, 4.0),
}

_DEFAULT_PLANNER_RATES: tuple[float, float] = MODEL_PRICING["claude-sonnet"]
_DEFAULT_REVIEWER_RATES: tuple[float, float] = MODEL_PRICING["claude-opus"]


def _rates_for_model(model: str) -> tuple[float, float]:
    """Look up (input, output) rates per million tokens for a model ID.

    Matches on the longest prefix found in MODEL_PRICING. Falls back to
    Sonnet rates if no match.

    Args:
        model: Full model ID (e.g., "claude-sonnet-4-20250514").

    Returns:
        (input_rate_per_M, output_rate_per_M) tuple.
    """
    for prefix in sorted(MODEL_PRICING, key=len, reverse=True):
        if model.startswith(prefix):
            return MODEL_PRICING[prefix]
    return _DEFAULT_PLANNER_RATES


# ---------------------------------------------------------------------------
# Per-persona result
# ---------------------------------------------------------------------------

@dataclass
class PersonaResult:
    """Result of running one persona through the orchestrator.

    Attributes:
        persona_id: Which persona was evaluated.
        plan_text: The generated plan text.
        approved: Whether the reviewer approved the plan.
        retry_count: Number of planner-reviewer cycles (orchestrator retries).
        total_iterations: Total planner+reviewer agent iterations across all retries.
        final_scores: Reviewer scores from the last review (None if never reviewed).
        decision_log: Per-iteration records from the orchestration loop.
        planner_input_tokens: Total planner input tokens across all retries.
        planner_output_tokens: Total planner output tokens across all retries.
        reviewer_input_tokens: Total reviewer input tokens across all retries.
        reviewer_output_tokens: Total reviewer output tokens across all retries.
        elapsed_seconds: Wall-clock time for this persona's evaluation.
        constraint_violations: Specific violations found in post-hoc analysis.
        athlete_cache_key: Profile+model hash for deduplication.
        warning: Orchestrator warning (e.g., budget exceeded, max retries).
        error: Fatal error message if the run failed.
        planner_model: Model ID used for the planner.
        reviewer_model: Model ID used for the reviewer.
    """

    persona_id: str
    plan_text: str = ""
    approved: bool = False
    retry_count: int = 0
    total_iterations: int = 0
    final_scores: ReviewerScores | None = None
    decision_log: list[DecisionLogEntry] = field(default_factory=list)
    planner_input_tokens: int = 0
    planner_output_tokens: int = 0
    reviewer_input_tokens: int = 0
    reviewer_output_tokens: int = 0
    elapsed_seconds: float = 0.0
    constraint_violations: list[str] = field(default_factory=list)
    athlete_cache_key: str = ""
    warning: str | None = None
    error: str | None = None
    planner_model: str = ""
    reviewer_model: str = ""

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed across planner and reviewer.

        Returns:
            Sum of all input and output tokens.
        """
        return (
            self.planner_input_tokens
            + self.planner_output_tokens
            + self.reviewer_input_tokens
            + self.reviewer_output_tokens
        )

    @property
    def estimated_cost_usd(self) -> float:
        """Cost estimate based on actual models used.

        Uses MODEL_PRICING lookup keyed by model ID prefix. Falls back to
        Sonnet (planner) and Opus (reviewer) rates if models are not set.

        Returns:
            Estimated cost in USD.
        """
        p_in, p_out = (
            _rates_for_model(self.planner_model) if self.planner_model
            else _DEFAULT_PLANNER_RATES
        )
        r_in, r_out = (
            _rates_for_model(self.reviewer_model) if self.reviewer_model
            else _DEFAULT_REVIEWER_RATES
        )
        planner_cost = (
            self.planner_input_tokens * p_in / 1_000_000
            + self.planner_output_tokens * p_out / 1_000_000
        )
        reviewer_cost = (
            self.reviewer_input_tokens * r_in / 1_000_000
            + self.reviewer_output_tokens * r_out / 1_000_000
        )
        return planner_cost + reviewer_cost

    @property
    def has_violations(self) -> bool:
        """Whether any constraint violations were found.

        Returns:
            True if constraint_violations is non-empty.
        """
        return len(self.constraint_violations) > 0

    def summary(self) -> str:
        """Format a concise multi-line summary of this persona result.

        Handles None scores gracefully by displaying 'N/A'.

        Returns:
            Multi-line string suitable for CLI output.
        """
        if self.error:
            status = "ERROR"
        elif self.approved:
            status = "APPROVED"
        else:
            status = "REJECTED"

        if self.final_scores is not None:
            scores_line = (
                f"Scores: safety={self.final_scores.safety}, "
                f"progression={self.final_scores.progression}, "
                f"specificity={self.final_scores.specificity}, "
                f"feasibility={self.final_scores.feasibility} "
                f"(overall={self.final_scores.overall:.1f})"
            )
        else:
            scores_line = "Scores: N/A"

        planner_tokens = self.planner_input_tokens + self.planner_output_tokens
        reviewer_tokens = self.reviewer_input_tokens + self.reviewer_output_tokens

        lines = [
            f"Persona: {self.persona_id}",
            f"Status: {status}",
            scores_line,
            f"Tokens: {self.total_tokens:,} "
            f"(planner: {planner_tokens:,}, reviewer: {reviewer_tokens:,})",
            f"Cost: ${self.estimated_cost_usd:.4f}",
            f"Time: {self.elapsed_seconds:.1f}s",
            f"Violations: {len(self.constraint_violations)}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict of all fields.

        Returns:
            Dictionary with all PersonaResult fields. ReviewerScores and
            DecisionLogEntry objects are converted to dicts.
        """
        scores_dict = None
        if self.final_scores is not None:
            scores_dict = {
                "safety": self.final_scores.safety,
                "progression": self.final_scores.progression,
                "specificity": self.final_scores.specificity,
                "feasibility": self.final_scores.feasibility,
                "overall": self.final_scores.overall,
            }

        decision_log_dicts = [
            entry.model_dump(mode="json") for entry in self.decision_log
        ]

        return {
            "persona_id": self.persona_id,
            "plan_text": self.plan_text,
            "approved": self.approved,
            "retry_count": self.retry_count,
            "total_iterations": self.total_iterations,
            "final_scores": scores_dict,
            "decision_log": decision_log_dicts,
            "planner_input_tokens": self.planner_input_tokens,
            "planner_output_tokens": self.planner_output_tokens,
            "reviewer_input_tokens": self.reviewer_input_tokens,
            "reviewer_output_tokens": self.reviewer_output_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_seconds": self.elapsed_seconds,
            "constraint_violations": self.constraint_violations,
            "athlete_cache_key": self.athlete_cache_key,
            "warning": self.warning,
            "error": self.error,
            "planner_model": self.planner_model,
            "reviewer_model": self.reviewer_model,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

@dataclass
class HarnessMetrics:
    """Aggregate metrics across all personas in a harness run.

    Attributes:
        timestamp: When the harness run completed.
        total_personas: Number of personas evaluated.
        total_approved: Number of plans that were approved.
        total_with_violations: Number of plans with constraint violations.
        violation_rate: Fraction of plans with violations (0.0-1.0).
        avg_retry_count: Mean retries across all personas.
        avg_safety_score: Mean safety score (from reviewed plans only).
        min_safety_score: Lowest safety score across all reviewed plans.
        avg_overall_score: Mean weighted overall score (from reviewed plans only).
        avg_tokens: Mean total tokens per persona.
        avg_cost_usd: Mean estimated cost per persona.
        total_cost_usd: Sum of estimated costs across all personas.
        avg_elapsed_seconds: Mean wall-clock time per persona.
        max_elapsed_seconds: Slowest persona's wall-clock time.
        total_elapsed_seconds: Wall-clock time for the entire harness run.
        reviewer_model: Which model was used as reviewer.
        planner_model: Which model was used as planner.
        worst_persona_id: Persona with the lowest overall score (or lowest
            safety score if tied). Empty string if no scored results.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_personas: int = 0
    total_approved: int = 0
    total_with_violations: int = 0
    violation_rate: float = 0.0
    avg_retry_count: float = 0.0
    avg_safety_score: float = 0.0
    min_safety_score: float = 0.0
    avg_overall_score: float = 0.0
    avg_tokens: float = 0.0
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    avg_elapsed_seconds: float = 0.0
    max_elapsed_seconds: float = 0.0
    total_elapsed_seconds: float = 0.0
    reviewer_model: str = ""
    planner_model: str = ""
    worst_persona_id: str = ""

    @classmethod
    def from_results(
        cls,
        results: list[PersonaResult],
        *,
        planner_model: str = "",
        reviewer_model: str = "",
        total_elapsed_seconds: float = 0.0,
    ) -> HarnessMetrics:
        """Compute aggregate metrics from a list of persona results.

        Args:
            results: List of PersonaResult from the harness run.
            planner_model: Model ID used for the planner.
            reviewer_model: Model ID used for the reviewer.
            total_elapsed_seconds: Total wall-clock time for the run.

        Returns:
            Aggregated HarnessMetrics.
        """
        if not results:
            return cls(
                planner_model=planner_model,
                reviewer_model=reviewer_model,
                total_elapsed_seconds=total_elapsed_seconds,
            )

        n = len(results)
        approved = sum(1 for r in results if r.approved)
        with_violations = sum(1 for r in results if r.has_violations)

        # Score averages only from results that have scores
        scored = [r for r in results if r.final_scores is not None]
        avg_safety = (
            sum(r.final_scores.safety for r in scored if r.final_scores is not None)
            / len(scored)
            if scored
            else 0.0
        )
        min_safety = (
            min(r.final_scores.safety for r in scored if r.final_scores is not None)
            if scored
            else 0.0
        )
        avg_overall = (
            sum(r.final_scores.overall for r in scored if r.final_scores is not None)
            / len(scored)
            if scored
            else 0.0
        )

        total_cost = sum(r.estimated_cost_usd for r in results)

        # Find worst persona: lowest overall score, break ties by lowest safety
        worst_pid = ""
        if scored:
            worst = min(
                scored,
                key=lambda r: (
                    r.final_scores.overall if r.final_scores is not None else float("inf"),
                    r.final_scores.safety if r.final_scores is not None else float("inf"),
                ),
            )
            worst_pid = worst.persona_id

        return cls(
            total_personas=n,
            total_approved=approved,
            total_with_violations=with_violations,
            violation_rate=with_violations / n,
            avg_retry_count=sum(r.retry_count for r in results) / n,
            avg_safety_score=avg_safety,
            min_safety_score=min_safety,
            avg_overall_score=avg_overall,
            avg_tokens=sum(r.total_tokens for r in results) / n,
            avg_cost_usd=total_cost / n,
            total_cost_usd=total_cost,
            avg_elapsed_seconds=sum(r.elapsed_seconds for r in results) / n,
            max_elapsed_seconds=max(r.elapsed_seconds for r in results),
            total_elapsed_seconds=total_elapsed_seconds,
            planner_model=planner_model,
            reviewer_model=reviewer_model,
            worst_persona_id=worst_pid,
        )

    def summary(self) -> str:
        """Format key metrics as a human-readable report block.

        Returns:
            Multi-line string suitable for CLI output.
        """
        lines = [
            "Evaluation Harness Results",
            "=" * 40,
            f"Models: planner={self.planner_model or '(default)'}, "
            f"reviewer={self.reviewer_model or '(default)'}",
            f"Personas: {self.total_personas}",
            f"Approved: {self.total_approved}/{self.total_personas}",
            f"Violation rate: {self.violation_rate:.1%}",
            f"Avg retries: {self.avg_retry_count:.1f}",
            f"Avg safety score: {self.avg_safety_score:.1f}",
            f"Min safety score: {self.min_safety_score:.0f}",
            f"Avg overall score: {self.avg_overall_score:.1f}",
            f"Avg tokens/persona: {self.avg_tokens:,.0f}",
            f"Avg cost/persona: ${self.avg_cost_usd:.4f}",
            f"Total cost: ${self.total_cost_usd:.4f}",
            f"Avg time/persona: {self.avg_elapsed_seconds:.1f}s",
            f"Max time (slowest): {self.max_elapsed_seconds:.1f}s",
            f"Total time: {self.total_elapsed_seconds:.1f}s",
        ]
        if self.worst_persona_id:
            lines.append(f"Worst persona: {self.worst_persona_id}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict of all fields.

        Converts the timestamp to ISO 8601 string format.

        Returns:
            Dictionary with all HarnessMetrics fields.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_personas": self.total_personas,
            "total_approved": self.total_approved,
            "total_with_violations": self.total_with_violations,
            "violation_rate": self.violation_rate,
            "avg_retry_count": self.avg_retry_count,
            "avg_safety_score": self.avg_safety_score,
            "min_safety_score": self.min_safety_score,
            "avg_overall_score": self.avg_overall_score,
            "avg_tokens": self.avg_tokens,
            "avg_cost_usd": self.avg_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "avg_elapsed_seconds": self.avg_elapsed_seconds,
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "reviewer_model": self.reviewer_model,
            "planner_model": self.planner_model,
            "worst_persona_id": self.worst_persona_id,
        }
