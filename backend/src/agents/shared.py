"""Shared utilities for planner and reviewer agents.

Extracts duplicated code: tool registry construction and text extraction
from Claude API response content blocks.
"""

from __future__ import annotations

from typing import Any

from src.tools.registry import ToolRegistry

__all__ = ["build_registry", "extract_text"]


def build_registry() -> ToolRegistry:
    """Create a ToolRegistry with all five MileMind tools.

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

    compute_training_stress.register(registry)
    evaluate_fatigue_state.register(registry)
    validate_progression_constraints.register(registry)
    simulate_race_outcomes.register(registry)
    reallocate_week_load.register(registry)

    return registry


def extract_text(content_blocks: list[Any]) -> str:
    """Extract concatenated text from Claude's response content blocks.

    Filters for blocks with ``type == "text"`` and joins their text
    with newlines. Non-text blocks (e.g., tool_use) are silently skipped.
    Returns an empty string if no text blocks are present.

    Args:
        content_blocks: The content list from a Claude API response.

    Returns:
        Concatenated text from all text blocks, joined by newlines.
        Empty string if content_blocks is empty or contains no text blocks.
    """
    text_parts: list[str] = []
    for block in content_blocks:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    return "\n".join(text_parts)
