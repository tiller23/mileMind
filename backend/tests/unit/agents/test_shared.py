"""Unit tests for shared agent utilities (extract_text, build_registry, AgentLoopResult, run_agent_loop)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.agents.shared import AgentLoopResult, build_registry, extract_text, run_agent_loop

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
        """Blocks without a 'type' attribute are silently skipped (W12)."""
        block_no_type: Any = {"text": "should be skipped"}
        assert extract_text([block_no_type]) == ""

    def test_block_without_text_attribute(self) -> None:
        """Blocks with 'type' but no 'text' attribute are skipped (W12)."""

        @dataclass
        class TypeOnlyBlock:
            type: str

        block: Any = TypeOnlyBlock(type="text")
        assert extract_text([block]) == ""

    def test_dict_block_with_type_key_skipped(self) -> None:
        """Dict blocks are skipped because hasattr checks fail (W12)."""
        block: Any = {"type": "text", "text": "should be skipped"}
        assert extract_text([block]) == ""

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

    def test_returns_registry_with_six_tools(self) -> None:
        registry = build_registry()
        tools = registry.get_anthropic_tools()
        assert len(tools) == 6

    def test_expected_tool_names(self) -> None:
        registry = build_registry()
        names = {t["name"] for t in registry.get_anthropic_tools()}
        assert names == {
            "compute_training_stress",
            "evaluate_fatigue_state",
            "validate_progression_constraints",
            "simulate_race_outcomes",
            "reallocate_week_load",
            "project_taper",
        }


# ---------------------------------------------------------------------------
# AgentLoopResult tests
# ---------------------------------------------------------------------------


class TestAgentLoopResult:
    """Tests for the AgentLoopResult dataclass."""

    def test_defaults(self) -> None:
        result = AgentLoopResult(final_text="test")
        assert result.final_text == "test"
        assert result.tool_calls == []
        assert result.iterations == 0
        assert result.total_input_tokens == 0
        assert result.total_output_tokens == 0
        assert result.stop_reason == ""

    def test_all_fields(self) -> None:
        result = AgentLoopResult(
            final_text="plan",
            tool_calls=[{"name": "t", "input": {}, "output": {}, "success": True}],
            iterations=3,
            total_input_tokens=500,
            total_output_tokens=1000,
            stop_reason="end_turn",
        )
        assert result.iterations == 3
        assert len(result.tool_calls) == 1
        assert result.stop_reason == "end_turn"


# ---------------------------------------------------------------------------
# Mock helpers for run_agent_loop
# ---------------------------------------------------------------------------


@dataclass
class _MockUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class _MockTextBlock:
    type: str = "text"
    text: str = "Done."


@dataclass
class _MockToolUseBlock:
    type: str = "tool_use"
    name: str = "compute_training_stress"
    input: dict = None  # type: ignore[assignment]
    id: str = "tu_123"

    def __post_init__(self) -> None:
        if self.input is None:
            self.input = {
                "workout_type": "easy",
                "duration_minutes": 30,
                "intensity": 0.6,
            }


@dataclass
class _MockResponse:
    stop_reason: str = "end_turn"
    content: list = None  # type: ignore[assignment]
    usage: _MockUsage = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.content is None:
            self.content = [_MockTextBlock()]
        if self.usage is None:
            self.usage = _MockUsage()


class _MockTransport:
    """A fake MessageTransport that returns pre-configured responses."""

    def __init__(self, responses: list[_MockResponse]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    async def create_message(self, **kwargs: Any) -> _MockResponse:
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


# ---------------------------------------------------------------------------
# run_agent_loop tests
# ---------------------------------------------------------------------------


class TestRunAgentLoop:
    """Direct unit tests for the run_agent_loop async function."""

    @pytest.mark.asyncio
    async def test_end_turn_returns_text(self) -> None:
        """Single end_turn response returns final text immediately."""
        transport = _MockTransport([_MockResponse()])
        registry = build_registry()
        tools = registry.get_anthropic_tools()

        result = await run_agent_loop(
            transport=transport,
            model="test-model",
            max_tokens=1024,
            system_prompt="You are a test.",
            tools=tools,
            messages=[{"role": "user", "content": "hello"}],
            registry=registry,
            max_iterations=5,
        )
        assert result.stop_reason == "end_turn"
        assert result.final_text == "Done."
        assert result.iterations == 1
        assert result.total_input_tokens == 100
        assert result.total_output_tokens == 50

    @pytest.mark.asyncio
    async def test_tool_use_then_end_turn(self) -> None:
        """Tool use followed by end_turn: tool is executed and results logged."""
        tool_response = _MockResponse(
            stop_reason="tool_use",
            content=[_MockToolUseBlock()],
            usage=_MockUsage(input_tokens=200, output_tokens=100),
        )
        final_response = _MockResponse(
            stop_reason="end_turn",
            content=[_MockTextBlock(text="Plan complete.")],
            usage=_MockUsage(input_tokens=300, output_tokens=150),
        )
        transport = _MockTransport([tool_response, final_response])
        registry = build_registry()
        tools = registry.get_anthropic_tools()

        result = await run_agent_loop(
            transport=transport,
            model="test-model",
            max_tokens=1024,
            system_prompt="You are a test.",
            tools=tools,
            messages=[{"role": "user", "content": "compute stress"}],
            registry=registry,
            max_iterations=5,
        )
        assert result.stop_reason == "end_turn"
        assert result.final_text == "Plan complete."
        assert result.iterations == 2
        assert result.total_input_tokens == 500
        assert result.total_output_tokens == 250
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "compute_training_stress"
        assert result.tool_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_max_iterations_cap(self) -> None:
        """Loop stops at max_iterations even if Claude keeps requesting tools."""
        tool_resp = _MockResponse(
            stop_reason="tool_use",
            content=[_MockToolUseBlock()],
        )
        transport = _MockTransport([tool_resp, tool_resp, tool_resp])
        registry = build_registry()
        tools = registry.get_anthropic_tools()

        result = await run_agent_loop(
            transport=transport,
            model="test-model",
            max_tokens=1024,
            system_prompt="You are a test.",
            tools=tools,
            messages=[{"role": "user", "content": "go"}],
            registry=registry,
            max_iterations=3,
        )
        assert result.stop_reason == "max_iterations"
        assert result.iterations == 3
        assert result.final_text == ""

    @pytest.mark.asyncio
    async def test_unexpected_stop_reason(self) -> None:
        """Unexpected stop reason (e.g. max_tokens) returns early."""
        resp = _MockResponse(
            stop_reason="max_tokens",
            content=[_MockTextBlock(text="Partial output")],
        )
        transport = _MockTransport([resp])
        registry = build_registry()
        tools = registry.get_anthropic_tools()

        result = await run_agent_loop(
            transport=transport,
            model="test-model",
            max_tokens=1024,
            system_prompt="You are a test.",
            tools=tools,
            messages=[{"role": "user", "content": "go"}],
            registry=registry,
            max_iterations=5,
        )
        assert result.stop_reason == "max_tokens"
        assert result.final_text == "Partial output"
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_token_accumulation_across_iterations(self) -> None:
        """Tokens from all iterations are summed correctly."""
        tool_resp = _MockResponse(
            stop_reason="tool_use",
            content=[_MockToolUseBlock()],
            usage=_MockUsage(input_tokens=100, output_tokens=50),
        )
        final_resp = _MockResponse(
            stop_reason="end_turn",
            content=[_MockTextBlock(text="Done.")],
            usage=_MockUsage(input_tokens=200, output_tokens=75),
        )
        transport = _MockTransport([tool_resp, final_resp])
        registry = build_registry()
        tools = registry.get_anthropic_tools()

        result = await run_agent_loop(
            transport=transport,
            model="test-model",
            max_tokens=1024,
            system_prompt="You are a test.",
            tools=tools,
            messages=[{"role": "user", "content": "go"}],
            registry=registry,
            max_iterations=10,
        )
        assert result.total_input_tokens == 300
        assert result.total_output_tokens == 125

    @pytest.mark.asyncio
    async def test_messages_mutated_in_place(self) -> None:
        """The messages list is mutated with assistant/tool_result entries."""
        tool_resp = _MockResponse(
            stop_reason="tool_use",
            content=[_MockToolUseBlock()],
        )
        final_resp = _MockResponse(
            stop_reason="end_turn",
            content=[_MockTextBlock(text="Done.")],
        )
        transport = _MockTransport([tool_resp, final_resp])
        registry = build_registry()
        tools = registry.get_anthropic_tools()
        messages: list[dict[str, Any]] = [{"role": "user", "content": "go"}]

        await run_agent_loop(
            transport=transport,
            model="test-model",
            max_tokens=1024,
            system_prompt="You are a test.",
            tools=tools,
            messages=messages,
            registry=registry,
            max_iterations=5,
        )
        # Original user message + assistant (tool_use) + user (tool_result) = 3
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
