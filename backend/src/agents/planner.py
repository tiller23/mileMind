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
from typing import Any

import anthropic

from src.agents.prompts import PLANNER_SYSTEM_PROMPT
from src.agents.validation import ValidationResult, validate_plan_output
from src.models.athlete import AthleteProfile
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def _build_registry() -> ToolRegistry:
    """Create a ToolRegistry and register all five MileMind tools.

    Returns:
        A fully populated ToolRegistry ready for the agent loop.
    """
    registry = ToolRegistry()

    # Import and register each tool module's register() function.
    from src.tools import compute_training_stress
    from src.tools import evaluate_fatigue_state
    from src.tools import validate_progression_constraints
    from src.tools import simulate_race_outcomes
    from src.tools import reallocate_week_load

    compute_training_stress.register(registry)
    evaluate_fatigue_state.register(registry)
    validate_progression_constraints.register(registry)
    simulate_race_outcomes.register(registry)
    reallocate_week_load.register(registry)

    return registry


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
            environment variable if not provided.
        model: Claude model identifier. Defaults to claude-sonnet-4-20250514.
        max_iterations: Maximum number of API round-trips before forcing a
            stop. Prevents infinite tool-use loops. Defaults to 30.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 30,
    ) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No API key provided. Pass api_key or set the ANTHROPIC_API_KEY "
                "environment variable."
            )

        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)
        self._model = model
        self._max_iterations = max_iterations
        self._registry = _build_registry()

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
            logger.error("Anthropic API error during plan generation: %s", e)
            return PlannerResult(
                plan_text="",
                error=f"Anthropic API error: {e}",
                validation=ValidationResult(
                    passed=False,
                    issues=[f"Anthropic API error: {e}"],
                ),
            )
        except Exception as e:
            logger.error("Unexpected error during plan generation: %s", e, exc_info=True)
            return PlannerResult(
                plan_text="",
                error=f"Unexpected error: {type(e).__name__}: {e}",
                validation=ValidationResult(
                    passed=False,
                    issues=[f"Unexpected error: {type(e).__name__}: {e}"],
                ),
            )

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
            logger.error("Anthropic API error during plan revision: %s", e)
            return PlannerResult(
                plan_text="",
                error=f"Anthropic API error: {e}",
                validation=ValidationResult(
                    passed=False,
                    issues=[f"Anthropic API error: {e}"],
                ),
            )
        except Exception as e:
            logger.error("Unexpected error during plan revision: %s", e, exc_info=True)
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

        On each iteration:
        1. Send messages to Claude with the system prompt and tool definitions.
        2. If stop_reason is "tool_use", execute each tool call via the registry,
           append tool results to the conversation, and loop.
        3. If stop_reason is "end_turn", extract the final text and return.
        4. If max_iterations is reached, return with whatever text is available
           plus an error note.

        Args:
            messages: The conversation messages (starts with user message).

        Returns:
            PlannerResult with accumulated data from the full run.
        """
        tool_definitions = self._registry.get_anthropic_tools()
        tool_call_log: list[dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        iterations = 0

        for iteration in range(1, self._max_iterations + 1):
            iterations = iteration

            logger.info(
                "Planner agent iteration %d/%d (messages: %d)",
                iteration, self._max_iterations, len(messages),
            )

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                system=PLANNER_SYSTEM_PROMPT,
                tools=tool_definitions,
                messages=messages,
            )

            # Track token usage
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            logger.info(
                "Iteration %d: stop_reason=%s, tokens(in=%d, out=%d)",
                iteration,
                response.stop_reason,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

            # If Claude is done (no more tool calls), extract final text
            if response.stop_reason == "end_turn":
                plan_text = self._extract_text(response.content)
                return PlannerResult(
                    plan_text=plan_text,
                    tool_calls=tool_call_log,
                    iterations=iterations,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            # If Claude wants to use tools, process them
            if response.stop_reason == "tool_use":
                # Append the assistant's full response (text + tool_use blocks)
                messages.append({"role": "assistant", "content": response.content})

                # Execute each tool call and collect results
                tool_result_blocks: list[dict[str, Any]] = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    logger.info(
                        "Executing tool: %s (id=%s)", tool_name, tool_use_id,
                    )

                    result = self._registry.execute(tool_name, tool_input)

                    tool_call_log.append({
                        "name": tool_name,
                        "input": tool_input,
                        "output": result.output,
                        "success": result.success,
                    })

                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result.to_content_block(),
                        "is_error": not result.success,
                    })

                # Append all tool results in a single user message
                messages.append({"role": "user", "content": tool_result_blocks})
            else:
                # Unexpected stop reason (e.g., max_tokens hit)
                plan_text = self._extract_text(response.content)
                return PlannerResult(
                    plan_text=plan_text,
                    tool_calls=tool_call_log,
                    iterations=iterations,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                    error=(
                        f"Unexpected stop_reason: {response.stop_reason}. "
                        "Response may be incomplete."
                    ),
                )

        # Max iterations reached without a final response
        logger.warning(
            "Planner agent hit max iterations (%d) without completing.",
            self._max_iterations,
        )
        return PlannerResult(
            plan_text="",
            tool_calls=tool_call_log,
            iterations=iterations,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            error=(
                f"Agent did not complete within {self._max_iterations} iterations. "
                "Plan generation was capped to prevent infinite loops."
            ),
        )

    @staticmethod
    def _extract_text(content_blocks: list[Any]) -> str:
        """Extract concatenated text from Claude's response content blocks.

        Args:
            content_blocks: The content list from a Claude API response. May
                contain text blocks, tool_use blocks, or other types.

        Returns:
            Concatenated text from all text blocks, separated by newlines.
        """
        text_parts: list[str] = []
        for block in content_blocks:
            if hasattr(block, "type") and block.type == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts)

    @staticmethod
    def _build_user_message(athlete: AthleteProfile) -> str:
        """Build the initial user message from an athlete profile.

        Serializes the athlete profile into a structured prompt that gives
        Claude all the information needed to design a training plan.

        Args:
            athlete: The athlete profile to serialize.

        Returns:
            A formatted string containing the athlete's data and the planning
            request.
        """
        profile_data = athlete.model_dump(exclude_none=True)
        profile_json = json.dumps(profile_data, indent=2)

        return (
            f"Please generate a periodized training plan for this athlete.\n\n"
            f"## Athlete Profile\n"
            f"```json\n{profile_json}\n```\n\n"
            f"## Instructions\n"
            f"- Design a multi-week plan targeting the {athlete.goal_distance} distance.\n"
            f"- The athlete trains {athlete.training_days_per_week} days per week.\n"
            f"- Current weekly mileage baseline: {athlete.weekly_mileage_base} km.\n"
            f"- Risk tolerance: {athlete.risk_tolerance.value}.\n"
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
            + (
                f"- Injury history: {athlete.injury_history}\n"
                if athlete.injury_history
                else ""
            )
            + (
                f"\nUse compute_training_stress for every workout, "
                f"validate_progression_constraints for the weekly load sequence, "
                f"and simulate_race_outcomes if VDOT data is available. "
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
        profile_data = athlete.model_dump(exclude_none=True)
        profile_json = json.dumps(profile_data, indent=2)

        issues_text = "\n".join(f"  - {issue}" for issue in reviewer_issues)
        if not issues_text:
            issues_text = "  (no specific issues listed)"

        return (
            f"Your previous training plan was REJECTED by the reviewer. "
            f"Please revise it to address the issues below.\n\n"
            f"## Athlete Profile\n"
            f"```json\n{profile_json}\n```\n\n"
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
            f"load sequence.\n"
            f"- Return the complete revised plan as a ```json block.\n"
            f"- Do NOT just patch the old plan — regenerate with corrections.\n"
        )
