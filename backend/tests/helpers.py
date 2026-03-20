"""Shared mock helpers for MileMind unit and integration tests.

Provides lightweight dataclasses that simulate Anthropic API response shapes
without network calls. Importable from any test module.

Usage:
    from tests.helpers import (
        MockContentBlock,
        MockUsage,
        MockResponse,
        make_tool_use_response,
        make_end_turn_response,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockContentBlock:
    """Simulates an Anthropic API content block.

    Mirrors the shape that agents inspect via block.type, block.text,
    block.name, block.input, and block.id.

    Attributes:
        type: Block type string — "text" or "tool_use".
        text: Text payload (used when type=="text").
        name: Tool name (used when type=="tool_use").
        input: Tool input dict (used when type=="tool_use").
        id: Tool use ID string (used when type=="tool_use").
    """

    type: str
    text: str = ""
    name: str = ""
    input: dict[str, Any] | None = None
    id: str = ""


@dataclass
class MockUsage:
    """Simulates Anthropic API usage statistics.

    Attributes:
        input_tokens: Number of input tokens for the request.
        output_tokens: Number of output tokens in the response.
    """

    input_tokens: int = 100
    output_tokens: int = 200


@dataclass
class MockResponse:
    """Simulates a complete Anthropic API messages.create() response.

    Attributes:
        content: List of content blocks in the response.
        stop_reason: Why the model stopped — "end_turn" or "tool_use".
        usage: Token usage statistics.
    """

    content: list[MockContentBlock]
    stop_reason: str
    usage: MockUsage = field(default_factory=MockUsage)


def make_tool_use_response(
    tool_calls: list[dict[str, Any]],
    text_before: str = "",
) -> MockResponse:
    """Build a mock response with tool_use blocks.

    Constructs a response that simulates Claude requesting one or more
    tool calls. The agent loop detects stop_reason="tool_use" and executes
    each block via the registry.

    Args:
        tool_calls: List of dicts, each with keys: name (str), input (dict),
            and optionally id (str). Missing id gets an auto-generated value.
        text_before: Optional text block to prepend before the tool blocks.

    Returns:
        MockResponse with stop_reason="tool_use".
    """
    blocks: list[MockContentBlock] = []
    if text_before:
        blocks.append(MockContentBlock(type="text", text=text_before))
    for i, tc in enumerate(tool_calls):
        blocks.append(MockContentBlock(
            type="tool_use",
            name=tc["name"],
            input=tc["input"],
            id=tc.get("id", f"toolu_{i:04d}"),
        ))
    return MockResponse(content=blocks, stop_reason="tool_use", usage=MockUsage())


def make_end_turn_response(text: str) -> MockResponse:
    """Build a mock response with a final text block.

    Simulates Claude producing a terminal text response (no more tool calls).
    The agent loop detects stop_reason="end_turn" and returns the plan text.

    Args:
        text: The final text content to return.

    Returns:
        MockResponse with stop_reason="end_turn".
    """
    return MockResponse(
        content=[MockContentBlock(type="text", text=text)],
        stop_reason="end_turn",
        usage=MockUsage(),
    )


def make_verdict_response(
    approved: bool,
    scores: dict[str, int],
    critique: str = "Looks good.",
    issues: list[str] | None = None,
) -> MockResponse:
    """Build a mock response containing a JSON verdict block for the reviewer.

    Constructs the fenced ```json block format that ReviewerAgent._parse_review_verdict
    expects. Scores are the raw integer dict (safety, progression, specificity, feasibility).

    Args:
        approved: Whether the plan is approved.
        scores: Dict with keys safety, progression, specificity, feasibility (0-100 each).
        critique: Reviewer's textual summary.
        issues: List of actionable issue strings (defaults to empty list).

    Returns:
        MockResponse with stop_reason="end_turn" and a ```json verdict block.
    """
    verdict = {
        "approved": approved,
        "scores": scores,
        "critique": critique,
        "issues": issues or [],
    }
    text = f"After reviewing the plan:\n\n```json\n{json.dumps(verdict, indent=2)}\n```"
    return MockResponse(
        content=[MockContentBlock(type="text", text=text)],
        stop_reason="end_turn",
        usage=MockUsage(),
    )
