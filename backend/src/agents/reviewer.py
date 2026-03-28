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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.tools.registry import ToolRegistry

import anthropic

from src.agents.prompts import REVIEWER_SYSTEM_PROMPT
from src.agents.shared import build_registry, run_agent_loop, sanitize_prompt_text
from src.agents.transport import AnthropicTransport, MessageTransport
from src.models.athlete import AthleteProfile
from src.models.decision_log import REVIEW_PASS_THRESHOLD, ReviewerScores

logger = logging.getLogger(__name__)


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
            Ignored if transport is given.
        model: Claude model identifier. Defaults to claude-opus-4-20250514.
        max_iterations: Maximum API round-trips. Defaults to 10.
        transport: Optional MessageTransport for API calls. If not provided,
            creates an AnthropicTransport from the resolved API key.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-opus-4-20250514",
        max_iterations: int = 10,
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

        Delegates to the shared ``run_agent_loop()`` and converts the generic
        ``AgentLoopResult`` into a ``ReviewerResult`` by parsing the verdict.

        Args:
            messages: The conversation messages (starts with user message).

        Returns:
            ReviewerResult parsed from the final text response.
        """
        loop_result = await run_agent_loop(
            transport=self._transport,
            model=self._model,
            max_tokens=4096,
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            tools=self._registry.get_anthropic_tools(),
            messages=messages,
            registry=self._registry,
            max_iterations=self._max_iterations,
            logger_name="Reviewer",
        )

        # Handle max_iterations case
        if loop_result.stop_reason == "max_iterations":
            return ReviewerResult(
                approved=False,
                tool_calls=loop_result.tool_calls,
                iterations=loop_result.iterations,
                total_input_tokens=loop_result.total_input_tokens,
                total_output_tokens=loop_result.total_output_tokens,
                error=(f"Reviewer did not complete within {self._max_iterations} iterations."),
            )

        # Parse the verdict from the final text
        result = self._parse_review_verdict(loop_result.final_text)
        result.tool_calls = loop_result.tool_calls
        result.iterations = loop_result.iterations
        result.total_input_tokens = loop_result.total_input_tokens
        result.total_output_tokens = loop_result.total_output_tokens

        # For unexpected stop reasons, add error if not already set
        if loop_result.stop_reason not in ("end_turn",) and not result.error:
            result.error = (
                f"Unexpected stop_reason: {loop_result.stop_reason}. "
                "Response may be incomplete."
            )

        return result

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
            idx = text.rfind('"approved"')
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
        required_keys = {"safety", "progression", "specificity", "feasibility"}
        if isinstance(raw_scores, dict):
            missing = required_keys - raw_scores.keys()
            if missing:
                return ReviewerResult(
                    approved=False,
                    critique=verdict.get("critique", ""),
                    error=f"Missing score keys in reviewer verdict: {sorted(missing)}",
                )
            try:
                scores = ReviewerScores(
                    safety=int(raw_scores["safety"]),
                    progression=int(raw_scores["progression"]),
                    specificity=int(raw_scores["specificity"]),
                    feasibility=int(raw_scores["feasibility"]),
                )
            except (ValueError, TypeError) as e:
                return ReviewerResult(
                    approved=False,
                    critique=verdict.get("critique", ""),
                    error=f"Invalid scores in reviewer verdict: {e}",
                )

        raw_approved = verdict.get("approved")
        if raw_approved is not True and raw_approved is not False:
            logger.warning(
                "Reviewer returned non-boolean 'approved' value: %r (treating as rejected)",
                raw_approved,
            )

        return ReviewerResult(
            approved=raw_approved is True,
            scores=scores,
            critique=str(verdict.get("critique", "")),
            issues=[str(i) for i in verdict.get("issues", []) if i is not None],
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

        # Sanitize plan text (LLM-generated, but could carry indirect injection
        # if user input flowed through the planner into plan output)
        sanitized_plan = sanitize_prompt_text(plan_text)

        return (
            f"Please review the following training plan.\n\n"
            f"## Athlete Profile\n"
            f"```json\n{profile_json}\n```\n\n"
            f"## Training Plan to Review\n"
            f"{sanitized_plan}\n\n"
            f"## Planner Tool Usage Summary\n"
            f"The planner made {len(planner_tool_calls)} tool call(s):\n"
            f"{tool_summary}\n\n"
            f"## Instructions\n"
            f"- Spot-check 2-3 key claims by calling tools independently.\n"
            f"- Score each dimension (safety, progression, specificity, feasibility) "
            f"from 0-100.\n"
            f"- Reject if any score is below {REVIEW_PASS_THRESHOLD}.\n"
            f"- Return your verdict as a ```json block.\n"
        )
