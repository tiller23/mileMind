"""Shared utilities for planner and reviewer agents.

Extracts duplicated code: tool registry construction, text extraction
from Claude API response content blocks, the generic agent loop, and
prompt sanitization for defense-in-depth against injection attacks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.agents.transport import MessageTransport
from src.tools.registry import ToolRegistry

__all__ = [
    "AgentLoopResult",
    "build_registry",
    "extract_text",
    "run_agent_loop",
    "sanitize_prompt_text",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt sanitization (shared by planner and reviewer)
# ---------------------------------------------------------------------------

# Known injection patterns. re.UNICODE ensures \s/\w match Cyrillic etc.
_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(?:ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions)"
    r"|(?:you\s+are\s+now\s+)"
    r"|(?:system\s*:\s*)"
    r"|(?:NEVER\s+(?:reject|fail|penalize))"
    r"|(?:always\s+approve)"
    r"|(?:override\s+(?:safety|constraints|rules))"
    r"|(?:disregard\s+(?:all\s+)?(?:previous|above|prior))"
    r"|(?:new\s+instructions?\s*:)"
    r"|(?:forget\s+(?:all\s+)?(?:previous|prior|everything))"
    r"|(?:act\s+as\s+(?:a\s+)?(?:different|new))"
    r"|(?:do\s+not\s+(?:follow|obey|listen))",
    re.UNICODE,
)

# Allowlist: letters, digits, basic punctuation, whitespace, medical symbols,
# JSON structural chars ({}[]), backticks (for code fences), comparison
# operators (<>), equals, pipe, tilde, caret, asterisk, underscore.
_ALLOWED_CHARS = re.compile(
    r"[^\w\s.,;:!?'\"()\-/+#%&@°\n\r\t{}\[\]`<>=|~^*_]",
    re.UNICODE,
)

# XML/HTML tag pattern — requires a letter after < to avoid matching
# comparison operators like "pace < 5:00" or "HR > 160".
_XML_TAG_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")


def sanitize_prompt_text(text: str) -> str:
    """Sanitize text before embedding in LLM prompts.

    Three-layer defense:
    1. Denylist: Known injection patterns replaced with [FILTERED].
    2. Tag stripping: XML/HTML tags removed (requires letter after <,
       so comparison operators like "< 5:00" are preserved).
    3. Allowlist: Only permitted characters survive.

    Used for user free-text (injury_history) and inter-agent text
    (reviewer critique flowing to planner, plan text flowing to reviewer).

    Args:
        text: Text to sanitize.

    Returns:
        Sanitized text.
    """
    sanitized = _INJECTION_PATTERNS.sub("[FILTERED]", text)
    sanitized = _XML_TAG_PATTERN.sub("", sanitized)
    sanitized = _ALLOWED_CHARS.sub("", sanitized)
    return sanitized.strip()


# ---------------------------------------------------------------------------
# AgentLoopResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentLoopResult:
    """Result of a generic agent tool-use loop.

    Attributes:
        final_text: Concatenated text from the final Claude response.
        tool_calls: Log of every tool call made during the run. Each entry
            is a dict with keys: name, input, output, success.
        iterations: Number of API round-trips (message.create calls) made.
        total_input_tokens: Cumulative input tokens across all iterations.
        total_output_tokens: Cumulative output tokens across all iterations.
        stop_reason: The stop_reason from the final API response, or
            "max_iterations" if the loop was capped.
    """

    final_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    stop_reason: str = ""


# ---------------------------------------------------------------------------
# build_registry
# ---------------------------------------------------------------------------

def build_registry() -> ToolRegistry:
    """Create a ToolRegistry with all six MileMind tools.

    Returns:
        A fully populated ToolRegistry.

    Raises:
        ValueError: If a tool name collision occurs during registration.
    """
    registry = ToolRegistry()

    from src.tools import compute_training_stress
    from src.tools import evaluate_fatigue_state
    from src.tools import validate_progression_constraints
    from src.tools import simulate_race_outcomes
    from src.tools import reallocate_week_load
    from src.tools import project_taper

    compute_training_stress.register(registry)
    evaluate_fatigue_state.register(registry)
    validate_progression_constraints.register(registry)
    simulate_race_outcomes.register(registry)
    reallocate_week_load.register(registry)
    project_taper.register(registry)

    return registry


# ---------------------------------------------------------------------------
# extract_text  (W12: proper type narrowing with hasattr checks)
# ---------------------------------------------------------------------------

def extract_text(content_blocks: list[Any]) -> str:
    """Extract concatenated text from Claude's response content blocks.

    Filters for blocks with ``type == "text"`` and joins their text
    with newlines. Non-text blocks (e.g., tool_use) are silently skipped.
    Returns an empty string if no text blocks are present.

    Uses explicit ``hasattr`` checks for type narrowing instead of
    duck-typing, ensuring blocks without ``type`` or ``text`` attributes
    are safely skipped.

    Args:
        content_blocks: The content list from a Claude API response.

    Returns:
        Concatenated text from all text blocks, joined by newlines.
        Empty string if content_blocks is empty or contains no text blocks.
    """
    text_parts: list[str] = []
    for block in content_blocks:
        if (
            hasattr(block, "type")
            and hasattr(block, "text")
            and block.type == "text"
        ):
            text_parts.append(block.text)
    return "\n".join(text_parts)


# ---------------------------------------------------------------------------
# run_agent_loop — generic tool-use loop shared by planner and reviewer
# ---------------------------------------------------------------------------

async def run_agent_loop(
    transport: MessageTransport,
    model: str,
    max_tokens: int,
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    registry: ToolRegistry,
    max_iterations: int,
    logger_name: str = "agent",
) -> AgentLoopResult:
    """Run the Claude tool-use loop until a final text response is produced.

    On each iteration:
    1. Send messages to Claude with the system prompt and tool definitions.
    2. If stop_reason is "tool_use", execute each tool call via the registry,
       append tool results to the conversation, and loop.
    3. If stop_reason is "end_turn", extract the final text and return.
    4. If max_iterations is reached, return with whatever text is available
       plus stop_reason="max_iterations".

    Any other stop_reason (e.g., "max_tokens") causes an early return with
    whatever text was produced and the actual stop_reason preserved.

    Args:
        transport: The MessageTransport for API calls.
        model: Claude model identifier.
        max_tokens: Maximum tokens per API call.
        system_prompt: The system prompt to use.
        tools: Tool definitions in Anthropic API format.
        messages: The conversation messages (starts with user message).
            Modified in place as the loop progresses.
        registry: The ToolRegistry for executing tool calls.
        max_iterations: Maximum number of API round-trips before forcing stop.
        logger_name: Name prefix for log messages (e.g., "Planner", "Reviewer").

    Returns:
        AgentLoopResult with accumulated data from the full run.
    """
    loop_logger = logging.getLogger(logger_name)
    tool_call_log: list[dict[str, Any]] = []
    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0

    for iteration in range(1, max_iterations + 1):
        iterations = iteration

        loop_logger.info(
            "%s agent iteration %d/%d, model=%s, messages=%d",
            logger_name, iteration, max_iterations, model, len(messages),
        )

        response = await transport.create_message(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        # Track token usage
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        tokens_this_iter = response.usage.input_tokens + response.usage.output_tokens
        loop_logger.info(
            "Iteration %d: stop_reason=%s, tokens_this_iter=%d (in=%d, out=%d)",
            iteration,
            response.stop_reason,
            tokens_this_iter,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        # If Claude is done (no more tool calls), extract final text
        if response.stop_reason == "end_turn":
            final_text = extract_text(response.content)
            return AgentLoopResult(
                final_text=final_text,
                tool_calls=tool_call_log,
                iterations=iterations,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                stop_reason="end_turn",
            )

        # If Claude wants to use tools, process them
        if response.stop_reason == "tool_use":
            # Append the assistant's full response (text + tool_use blocks).
            # NOTE: response.content contains SDK ContentBlock objects, not plain
            # dicts.  The Anthropic SDK accepts this mixed format (dict messages
            # with SDK content blocks) when the list is passed back on the next
            # create_message call.  This is intentional — serialising to dicts
            # would discard type information the SDK relies on internally.
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_result_blocks: list[dict[str, Any]] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                result = registry.execute(tool_name, tool_input)

                loop_logger.info(
                    "Tool call: tool=%s, success=%s", tool_name, result.success,
                )

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
            final_text = extract_text(response.content)
            return AgentLoopResult(
                final_text=final_text,
                tool_calls=tool_call_log,
                iterations=iterations,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                stop_reason=response.stop_reason,
            )

    # Max iterations reached without a final response
    loop_logger.warning(
        "%s agent hit max iterations (%d) without completing.",
        logger_name, max_iterations,
    )
    return AgentLoopResult(
        final_text="",
        tool_calls=tool_call_log,
        iterations=iterations,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        stop_reason="max_iterations",
    )
