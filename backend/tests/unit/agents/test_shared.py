"""Unit tests for shared agent utilities (extract_text, build_registry)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agents.shared import build_registry, extract_text


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

@dataclass
class MockBlock:
    """Simulates a Claude API content block."""
    type: str
    text: str = ""


# ---------------------------------------------------------------------------
# extract_text tests
# ---------------------------------------------------------------------------

class TestExtractText:
    """Tests for the extract_text utility."""

    def test_empty_list(self) -> None:
        assert extract_text([]) == ""

    def test_single_text_block(self) -> None:
        blocks = [MockBlock(type="text", text="Hello")]
        assert extract_text(blocks) == "Hello"

    def test_multiple_text_blocks_joined_with_newline(self) -> None:
        blocks = [
            MockBlock(type="text", text="Line 1"),
            MockBlock(type="text", text="Line 2"),
        ]
        assert extract_text(blocks) == "Line 1\nLine 2"

    def test_non_text_blocks_skipped(self) -> None:
        blocks = [
            MockBlock(type="tool_use"),
            MockBlock(type="text", text="Only this"),
            MockBlock(type="tool_result"),
        ]
        assert extract_text(blocks) == "Only this"

    def test_only_non_text_blocks(self) -> None:
        blocks = [MockBlock(type="tool_use"), MockBlock(type="tool_result")]
        assert extract_text(blocks) == ""

    def test_block_without_type_attribute(self) -> None:
        """Blocks without a 'type' attribute are silently skipped."""
        block_no_type: Any = {"text": "should be skipped"}
        assert extract_text([block_no_type]) == ""

    def test_mixed_with_empty_text(self) -> None:
        blocks = [
            MockBlock(type="text", text=""),
            MockBlock(type="text", text="content"),
        ]
        assert extract_text(blocks) == "\ncontent"


# ---------------------------------------------------------------------------
# build_registry tests
# ---------------------------------------------------------------------------

class TestBuildRegistry:
    """Tests for the build_registry utility."""

    def test_returns_registry_with_five_tools(self) -> None:
        registry = build_registry()
        tools = registry.get_anthropic_tools()
        assert len(tools) == 5

    def test_expected_tool_names(self) -> None:
        registry = build_registry()
        names = {t["name"] for t in registry.get_anthropic_tools()}
        assert names == {
            "compute_training_stress",
            "evaluate_fatigue_state",
            "validate_progression_constraints",
            "simulate_race_outcomes",
            "reallocate_week_load",
        }
