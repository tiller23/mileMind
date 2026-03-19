"""Planner agent — generates periodized training plans via Claude tool-use loop.

Uses the Anthropic async API to drive a multi-turn conversation where Claude
proposes workouts and calls deterministic tools to compute all physiological
metrics. The agent never generates TSS, CTL, ATL, TSB, ACWR, VO2max, or pace
values directly; every number traces back to a tool call.

Usage:
    planner = PlannerAgent(api_key="sk-...")
    result = await planner.generate_plan(athlete_profile)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.tools.registry import ToolRegistry

import anthropic

from src.agents.prompts import PLANNER_SYSTEM_PROMPT
from src.agents.shared import build_registry, run_agent_loop
from src.agents.transport import AnthropicTransport, MessageTransport
from src.agents.validation import ValidationResult, validate_plan_output
from src.models.athlete import AthleteProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlannerResult:
    """Result of a planner agent run.

    Attributes:
        plan_text: The raw text response from Claude containing the training plan.
        tool_calls: Log of every tool call made during the run. Each entry is a
            dict with keys: name, input, output, success.
        iterations: Number of API round-trips (message.create calls) made.
        total_input_tokens: Cumulative input tokens across all iterations.
        total_output_tokens: Cumulative output tokens across all iterations.
        error: Error message if the run failed, None on success.
    """

    plan_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error: str | None = None
    validation: ValidationResult | None = None


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------

class PlannerAgent:
    """Agent that generates periodized training plans using Claude and tools.

    The agent sends the athlete profile to Claude with the planner system prompt
    and tool definitions, then handles tool-use responses in a loop until Claude
    produces a final text response with the complete plan.

    Args:
        api_key: Anthropic API key. Falls back to the ANTHROPIC_API_KEY
            environment variable if not provided. Ignored if transport is given.
        model: Claude model identifier. Defaults to claude-sonnet-4-20250514.
        max_iterations: Maximum number of API round-trips before forcing a
            stop. Prevents infinite tool-use loops. Defaults to 15.
        transport: Optional MessageTransport for API calls. If not provided,
            creates an AnthropicTransport from the resolved API key.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 15,
        transport: MessageTransport | None = None,
    ) -> None:
        if transport is not None:
            self._transport = transport
        else:
            resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not resolved_key:
                raise ValueError(
                    "No API key provided. Pass api_key, set the ANTHROPIC_API_KEY "
                    "environment variable, or provide a transport."
                )
            self._transport = AnthropicTransport(api_key=resolved_key)

        self._model = model
        self._max_iterations = max_iterations
        self._registry = build_registry()

    @property
    def model(self) -> str:
        """The Claude model identifier used by this agent."""
        return self._model

    @property
    def registry(self) -> ToolRegistry:
        """The tool registry used by this agent."""
        return self._registry

    async def generate_plan(self, athlete: AthleteProfile) -> PlannerResult:
        """Generate a training plan for the given athlete profile.

        Builds the initial user message from the athlete's profile data and
        runs the agent loop until Claude produces a final text response or
        the iteration cap is reached.

        Args:
            athlete: The athlete profile containing goals, fitness data, and
                constraints.

        Returns:
            PlannerResult with the plan text, tool call log, and token usage.
        """
        user_message = self._build_user_message(athlete)
        return await self._generate_with_message(user_message)

    async def revise_plan(
        self,
        athlete: AthleteProfile,
        prior_plan_text: str,
        reviewer_critique: str,
        reviewer_issues: list[str],
    ) -> PlannerResult:
        """Revise a previously generated plan based on reviewer feedback.

        Builds a revision message containing the original athlete profile,
        the prior plan, and the reviewer's critique with specific issues.
        Reuses the same tool-use agent loop as generate_plan().

        Args:
            athlete: The athlete profile the plan was built for.
            prior_plan_text: The plan text that was rejected.
            reviewer_critique: The reviewer's textual critique.
            reviewer_issues: Specific issues the reviewer identified.

        Returns:
            PlannerResult with the revised plan text, tool call log, and
            token usage.
        """
        user_message = self._build_revision_message(
            athlete, prior_plan_text, reviewer_critique, reviewer_issues,
        )
        return await self._generate_with_message(user_message)

    async def _generate_with_message(self, user_message: str) -> PlannerResult:
        """Run the agent loop with a user message, validate, and handle errors.

        Does not raise; all exceptions (including anthropic.APIError) are
        captured into PlannerResult.error with a failed ValidationResult.

        Args:
            user_message: The user message to start the conversation with.

        Returns:
            PlannerResult with validation applied.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        try:
            result = await self._run_agent_loop(messages)
            result.validation = validate_plan_output(result.plan_text, result.tool_calls)
            if not result.validation.passed and result.error is None:
                result.error = (
                    "Output validation failed: "
                    + "; ".join(result.validation.issues)
                )
            return result
        except anthropic.APIError as e:
            logger.error("Anthropic API error: %s", e)
            return PlannerResult(
                plan_text="",
                error=f"Anthropic API error: {e}",
                validation=ValidationResult(
                    passed=False,
                    issues=[f"Anthropic API error: {e}"],
                ),
            )
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)
            return PlannerResult(
                plan_text="",
                error=f"Unexpected error: {type(e).__name__}: {e}",
                validation=ValidationResult(
                    passed=False,
                    issues=[f"Unexpected error: {type(e).__name__}: {e}"],
                ),
            )

    async def _run_agent_loop(self, messages: list[dict[str, Any]]) -> PlannerResult:
        """Run the Claude tool-use loop until a final text response is produced.

        Delegates to the shared ``run_agent_loop()`` and converts the generic
        ``AgentLoopResult`` into a ``PlannerResult``.

        Args:
            messages: The conversation messages (starts with user message).

        Returns:
            PlannerResult with accumulated data from the full run.
        """
        loop_result = await run_agent_loop(
            transport=self._transport,
            model=self._model,
            max_tokens=8192,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            tools=self._registry.get_anthropic_tools(),
            messages=messages,
            registry=self._registry,
            max_iterations=self._max_iterations,
            logger_name="Planner",
        )

        # Map stop_reason to error message
        error: str | None = None
        if loop_result.stop_reason == "max_iterations":
            error = (
                f"Agent did not complete within {self._max_iterations} iterations. "
                "Plan generation was capped to prevent infinite loops."
            )
        elif loop_result.stop_reason not in ("end_turn",):
            error = (
                f"Unexpected stop_reason: {loop_result.stop_reason}. "
                "Response may be incomplete."
            )

        return PlannerResult(
            plan_text=loop_result.final_text,
            tool_calls=loop_result.tool_calls,
            iterations=loop_result.iterations,
            total_input_tokens=loop_result.total_input_tokens,
            total_output_tokens=loop_result.total_output_tokens,
            error=error,
        )

    @staticmethod
    def _classify_athlete_level(athlete: AthleteProfile) -> str:
        """Classify athlete as beginner, intermediate, or advanced.

        Uses VDOT and weekly mileage base to determine level, which informs
        what workout types and intensities are appropriate.

        Args:
            athlete: The athlete profile to classify.

        Returns:
            One of "beginner", "intermediate", or "advanced".
        """
        vdot = athlete.vdot
        base = athlete.weekly_mileage_base

        # Advanced requires BOTH high base AND acceptable VDOT (or no VDOT data).
        # A runner with high VDOT but low base is undertrained, not advanced.
        if base > 60 and (vdot is None or vdot > 50):
            return "advanced"
        # Beginner if EITHER signal indicates low level — err on the side of safety.
        # Low base alone is enough; low VDOT with moderate base is still beginner.
        if base < 25 or (vdot is not None and vdot < 35):
            return "beginner"
        return "intermediate"

    @staticmethod
    def _build_user_message(athlete: AthleteProfile) -> str:
        """Build the initial user message from an athlete profile.

        Serializes the athlete profile into a structured prompt that gives
        Claude all the information needed to design a training plan. Includes
        athlete level classification and explicit safety constraints.

        Args:
            athlete: The athlete profile to serialize.

        Returns:
            A formatted string containing the athlete's data and the planning
            request.
        """
        profile_data = athlete.model_dump(exclude_none=True)
        profile_json = json.dumps(profile_data, indent=2)
        level = PlannerAgent._classify_athlete_level(athlete)

        # Build injury context with nuance
        injury_section = ""
        if athlete.injury_history:
            injury_section = (
                f"- Injury history: {athlete.injury_history}\n"
                f"  Apply the injury guidelines from your system prompt — "
                f"past healed injuries need strengthening notes, not blanket "
                f"restrictions. Only reduce training for recent/current issues.\n"
            )

        return (
            f"Please generate a periodized training plan for this athlete.\n\n"
            f"## Athlete Profile\n"
            f"```json\n{profile_json}\n```\n\n"
            f"## Athlete Level: {level.upper()}\n"
            f"Refer to the '{level}' section of your Athlete-Level Coaching "
            f"Guidelines for appropriate workout types and intensity.\n\n"
            f"## Safety Constraints (HARD LIMITS)\n"
            f"- Max weekly load increase: {athlete.max_weekly_increase_pct:.0%} "
            f"(athlete's max_weekly_increase_pct = {athlete.max_weekly_increase_pct})\n"
            f"- Risk tolerance: {athlete.risk_tolerance.value}\n"
            f"- Recovery weeks MUST appear every 3-4 building weeks\n"
            f"- Validate progression AFTER EACH PHASE with "
            f"validate_progression_constraints\n\n"
            f"## Instructions\n"
            f"- Design a multi-week plan targeting the {athlete.goal_distance} distance.\n"
            f"- The athlete trains {athlete.training_days_per_week} days per week.\n"
            f"- Current weekly mileage baseline: {athlete.weekly_mileage_base} km.\n"
            + (
                f"- Goal finish time: {athlete.goal_time_minutes} minutes.\n"
                if athlete.goal_time_minutes
                else ""
            )
            + (
                f"- VDOT: {athlete.vdot}.\n"
                if athlete.vdot
                else ""
            )
            + (
                f"- VO2max: {athlete.vo2max} ml/kg/min.\n"
                if athlete.vo2max
                else ""
            )
            + injury_section
            + (
                f"\nUse compute_training_stress for every workout, "
                f"validate_progression_constraints AFTER EACH PHASE "
                f"(not just at the end), "
                f"and simulate_race_outcomes if VDOT data is available. "
                f"Use Zone 1-6 pace zones in your plan. "
                f"Return the complete plan as a JSON block."
            )
        )

    @staticmethod
    def _build_revision_message(
        athlete: AthleteProfile,
        prior_plan_text: str,
        reviewer_critique: str,
        reviewer_issues: list[str],
    ) -> str:
        """Build a revision request message from reviewer feedback.

        Includes the original athlete profile, the rejected plan, and the
        reviewer's critique with specific issues to address.

        Args:
            athlete: The athlete profile the plan was built for.
            prior_plan_text: The plan that was rejected.
            reviewer_critique: The reviewer's textual assessment.
            reviewer_issues: Specific actionable issues to fix.

        Returns:
            A formatted revision request message.
        """
        # W11: Size guard — truncate oversized inputs to prevent token blowout
        _MAX_PLAN_CHARS = 50_000
        _MAX_CRITIQUE_CHARS = 10_000

        if len(prior_plan_text) > _MAX_PLAN_CHARS:
            logger.warning(
                "Truncating prior_plan_text from %d to %d chars",
                len(prior_plan_text), _MAX_PLAN_CHARS,
            )
            prior_plan_text = prior_plan_text[:_MAX_PLAN_CHARS] + "\n[...TRUNCATED]"

        if len(reviewer_critique) > _MAX_CRITIQUE_CHARS:
            logger.warning(
                "Truncating reviewer_critique from %d to %d chars",
                len(reviewer_critique), _MAX_CRITIQUE_CHARS,
            )
            reviewer_critique = reviewer_critique[:_MAX_CRITIQUE_CHARS] + "\n[...TRUNCATED]"

        profile_data = athlete.model_dump(exclude_none=True)
        profile_json = json.dumps(profile_data, indent=2)

        issues_text = "\n".join(f"  - {issue}" for issue in reviewer_issues)
        if not issues_text:
            issues_text = "  (no specific issues listed)"

        level = PlannerAgent._classify_athlete_level(athlete)

        return (
            f"Your previous training plan was REJECTED by the reviewer. "
            f"Please revise it to address the issues below.\n\n"
            f"## Athlete Profile\n"
            f"```json\n{profile_json}\n```\n\n"
            f"## Athlete Level: {level.upper()}\n\n"
            f"## Safety Constraints (HARD LIMITS — most common rejection reasons)\n"
            f"- Max weekly load increase: {athlete.max_weekly_increase_pct:.0%}\n"
            f"- Recovery weeks MUST appear every 3-4 building weeks\n"
            f"- Risk tolerance: {athlete.risk_tolerance.value}\n\n"
            f"## Previous Plan (REJECTED)\n"
            f"{prior_plan_text}\n\n"
            f"## Reviewer Critique\n"
            f"{reviewer_critique}\n\n"
            f"## Specific Issues to Fix\n"
            f"{issues_text}\n\n"
            f"## Revision Instructions\n"
            f"- Address EVERY issue listed above.\n"
            f"- Re-run compute_training_stress for any workouts you modify.\n"
            f"- Re-run validate_progression_constraints on the revised weekly "
            f"load sequence — validate AFTER EACH PHASE.\n"
            f"- Use Zone 1-6 pace zones.\n"
            f"- Return the complete revised plan as a ```json block.\n"
            f"- Do NOT just patch the old plan — regenerate with corrections.\n"
        )
