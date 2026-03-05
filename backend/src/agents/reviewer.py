"""Reviewer agent — independently evaluates training plans across 4 dimensions.

The reviewer receives a plan (without the planner's reasoning) and uses the
same deterministic tools to spot-check claims. It scores safety, progression,
specificity, and feasibility, then approves or rejects with actionable critique.

Usage:
    reviewer = ReviewerAgent(api_key="sk-...")
    result = await reviewer.review_plan(athlete, plan_text, planner_tool_calls)
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

from src.agents.prompts import REVIEWER_SYSTEM_PROMPT
from src.models.athlete import AthleteProfile
from src.models.decision_log import ReviewerScores
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool registration (same registry as planner)
# ---------------------------------------------------------------------------

def _build_registry() -> ToolRegistry:
    """Create a ToolRegistry with all five MileMind tools.

    Returns:
        A fully populated ToolRegistry.
    """
    registry = ToolRegistry()

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
class ReviewerResult:
    """Result of a reviewer agent run.

    Attributes:
        approved: Whether the plan was approved.
        scores: Dimension scores (None if parsing failed).
        critique: Reviewer's textual assessment.
        issues: Specific actionable issues for the planner.
        tool_calls: Log of tool calls made during review.
        iterations: Number of API round-trips.
        total_input_tokens: Cumulative input tokens.
        total_output_tokens: Cumulative output tokens.
        error: Error message if the run failed, None on success.
    """

    approved: bool
    scores: ReviewerScores | None = None
    critique: str = ""
    issues: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# ReviewerAgent
# ---------------------------------------------------------------------------

class ReviewerAgent:
    """Agent that reviews training plans using Claude and deterministic tools.

    The reviewer receives the plan text and athlete profile, spot-checks
    claims with tool calls, and produces a scored verdict.

    Args:
        api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        model: Claude model identifier. Defaults to claude-sonnet-4-20250514.
        max_iterations: Maximum API round-trips. Defaults to 15.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 15,
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

    async def review_plan(
        self,
        athlete: AthleteProfile,
        plan_text: str,
        planner_tool_calls: list[dict[str, Any]],
    ) -> ReviewerResult:
        """Review a training plan and produce a scored verdict.

        Args:
            athlete: The athlete profile the plan was built for.
            plan_text: The planner's raw text output containing the plan.
            planner_tool_calls: Log of tool calls the planner made (for context).

        Returns:
            ReviewerResult with approval status, scores, and critique.
        """
        user_message = self._build_review_message(athlete, plan_text, planner_tool_calls)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        try:
            return await self._run_agent_loop(messages)
        except anthropic.APIError as e:
            logger.error("Anthropic API error during review: %s", e)
            return ReviewerResult(
                approved=False,
                error=f"Anthropic API error: {e}",
            )
        except Exception as e:
            logger.error("Unexpected error during review: %s", e, exc_info=True)
            return ReviewerResult(
                approved=False,
                error=f"Unexpected error: {type(e).__name__}: {e}",
            )

    async def _run_agent_loop(self, messages: list[dict[str, Any]]) -> ReviewerResult:
        """Run the Claude tool-use loop until a verdict is produced.

        Same pattern as PlannerAgent._run_agent_loop(), but parses the
        final text as a review verdict instead of a training plan.

        Args:
            messages: The conversation messages (starts with user message).

        Returns:
            ReviewerResult parsed from the final text response.
        """
        tool_definitions = self._registry.get_anthropic_tools()
        tool_call_log: list[dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        iterations = 0

        for iteration in range(1, self._max_iterations + 1):
            iterations = iteration

            logger.info(
                "Reviewer agent iteration %d/%d (messages: %d)",
                iteration, self._max_iterations, len(messages),
            )

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=REVIEWER_SYSTEM_PROMPT,
                tools=tool_definitions,
                messages=messages,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            logger.info(
                "Iteration %d: stop_reason=%s, tokens(in=%d, out=%d)",
                iteration,
                response.stop_reason,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

            if response.stop_reason == "end_turn":
                verdict_text = self._extract_text(response.content)
                result = self._parse_review_verdict(verdict_text)
                result.tool_calls = tool_call_log
                result.iterations = iterations
                result.total_input_tokens = total_input_tokens
                result.total_output_tokens = total_output_tokens
                return result

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

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

                messages.append({"role": "user", "content": tool_result_blocks})
            else:
                verdict_text = self._extract_text(response.content)
                result = self._parse_review_verdict(verdict_text)
                result.tool_calls = tool_call_log
                result.iterations = iterations
                result.total_input_tokens = total_input_tokens
                result.total_output_tokens = total_output_tokens
                if not result.error:
                    result.error = (
                        f"Unexpected stop_reason: {response.stop_reason}. "
                        "Response may be incomplete."
                    )
                return result

        logger.warning(
            "Reviewer agent hit max iterations (%d) without completing.",
            self._max_iterations,
        )
        return ReviewerResult(
            approved=False,
            tool_calls=tool_call_log,
            iterations=iterations,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            error=(
                f"Reviewer did not complete within {self._max_iterations} iterations."
            ),
        )

    @staticmethod
    def _extract_text(content_blocks: list[Any]) -> str:
        """Extract concatenated text from Claude's response content blocks.

        Args:
            content_blocks: The content list from a Claude API response.

        Returns:
            Concatenated text from all text blocks.
        """
        text_parts: list[str] = []
        for block in content_blocks:
            if hasattr(block, "type") and block.type == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts)

    @staticmethod
    def _parse_review_verdict(text: str) -> ReviewerResult:
        """Extract the JSON verdict from the reviewer's text response.

        Looks for a ```json fenced block and parses it. Falls back to
        finding any JSON object with an "approved" key.

        Args:
            text: The reviewer's full text response.

        Returns:
            ReviewerResult parsed from the verdict JSON. On parse failure,
            returns a rejected result with an error message.
        """
        # Try to find ```json ... ``` block first
        json_match = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Fallback: find a JSON object containing "approved" by scanning
            # for balanced braces starting from the first '{' before "approved".
            idx = text.find('"approved"')
            if idx == -1:
                return ReviewerResult(
                    approved=False,
                    critique=text[:500] if text else "",
                    error="Could not find JSON verdict in reviewer response.",
                )
            # Walk backwards to find the opening brace
            start = text.rfind("{", 0, idx)
            if start == -1:
                return ReviewerResult(
                    approved=False,
                    critique=text[:500] if text else "",
                    error="Could not find JSON verdict in reviewer response.",
                )
            # Walk forward to find balanced closing brace
            depth = 0
            end = start
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            else:
                return ReviewerResult(
                    approved=False,
                    critique=text[:500] if text else "",
                    error="Could not find JSON verdict in reviewer response.",
                )
            json_str = text[start:end]

        try:
            verdict = json.loads(json_str)
        except json.JSONDecodeError as e:
            return ReviewerResult(
                approved=False,
                critique=text[:500] if text else "",
                error=f"Invalid JSON in reviewer verdict: {e}",
            )

        # Parse scores
        scores = None
        raw_scores = verdict.get("scores")
        if isinstance(raw_scores, dict):
            try:
                scores = ReviewerScores(
                    safety=int(raw_scores.get("safety", 0)),
                    progression=int(raw_scores.get("progression", 0)),
                    specificity=int(raw_scores.get("specificity", 0)),
                    feasibility=int(raw_scores.get("feasibility", 0)),
                )
            except (ValueError, TypeError) as e:
                return ReviewerResult(
                    approved=False,
                    critique=verdict.get("critique", ""),
                    error=f"Invalid scores in reviewer verdict: {e}",
                )

        return ReviewerResult(
            approved=bool(verdict.get("approved", False)),
            scores=scores,
            critique=str(verdict.get("critique", "")),
            issues=list(verdict.get("issues", [])),
        )

    @staticmethod
    def _build_review_message(
        athlete: AthleteProfile,
        plan_text: str,
        planner_tool_calls: list[dict[str, Any]],
    ) -> str:
        """Build the user message for the reviewer.

        Includes the athlete profile, the plan to review, and a summary
        of the planner's tool usage (so the reviewer knows what was computed
        vs. what might be fabricated).

        Args:
            athlete: The athlete profile.
            plan_text: The planner's output text.
            planner_tool_calls: Log of tool calls from the planner run.

        Returns:
            A formatted review request message.
        """
        profile_data = athlete.model_dump(exclude_none=True)
        profile_json = json.dumps(profile_data, indent=2)

        tool_summary_lines: list[str] = []
        for tc in planner_tool_calls:
            status = "OK" if tc.get("success", False) else "FAIL"
            tool_summary_lines.append(f"  - {tc['name']} [{status}]")
        tool_summary = "\n".join(tool_summary_lines) if tool_summary_lines else "  (none)"

        return (
            f"Please review the following training plan.\n\n"
            f"## Athlete Profile\n"
            f"```json\n{profile_json}\n```\n\n"
            f"## Training Plan to Review\n"
            f"{plan_text}\n\n"
            f"## Planner Tool Usage Summary\n"
            f"The planner made {len(planner_tool_calls)} tool call(s):\n"
            f"{tool_summary}\n\n"
            f"## Instructions\n"
            f"- Spot-check 2-3 key claims by calling tools independently.\n"
            f"- Score each dimension (safety, progression, specificity, feasibility) "
            f"from 0-100.\n"
            f"- Reject if any score is below 70.\n"
            f"- Return your verdict as a ```json block.\n"
        )
