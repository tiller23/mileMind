"""Integration tests for the planner agent.

Tests the full planner pipeline with a mocked Anthropic API client.
Verifies that:
- The agent loop correctly dispatches tool calls via the registry
- Tool results are fed back to the conversation
- Output validation catches missing tool calls
- The agent handles error scenarios gracefully

These tests do NOT call the real Anthropic API. They mock the client to
simulate Claude's tool-use responses, allowing us to verify the full
pipeline without API costs or network dependencies.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.shared import build_registry
from src.agents.prompts import PLANNER_SYSTEM_PROMPT
from src.agents.validation import ValidationResult, validate_plan_output
from src.models.athlete import AthleteProfile, RiskTolerance
from src.tools.registry import ToolRegistry
from tests.helpers import (
    MockContentBlock,
    MockResponse,
    MockUsage,
    make_end_turn_response,
    make_tool_use_response,
)


# sample_athlete fixture is provided by tests/conftest.py


@pytest.fixture
def registry() -> ToolRegistry:
    """A fully populated tool registry."""
    return build_registry()


# ---------------------------------------------------------------------------
# Tests: Registry builds correctly
# ---------------------------------------------------------------------------

class TestBuildRegistry:
    """Verify build_registry() creates a valid registry with all 6 tools."""

    def test_registry_has_five_tools(self, registry: ToolRegistry) -> None:
        assert len(registry.tool_names) == 6

    def test_expected_tool_names(self, registry: ToolRegistry) -> None:
        expected = {
            "compute_training_stress",
            "evaluate_fatigue_state",
            "validate_progression_constraints",
            "simulate_race_outcomes",
            "reallocate_week_load",
            "project_taper",
        }
        assert set(registry.tool_names) == expected

    def test_anthropic_tools_format(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        assert len(tools) == 6
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool


# ---------------------------------------------------------------------------
# Tests: Agent loop with mocked API
# ---------------------------------------------------------------------------

class TestPlannerAgentLoop:
    """Test the planner agent loop with mocked Anthropic client."""

    @pytest.fixture
    def mock_agent(self) -> PlannerAgent:
        """Create a PlannerAgent with a mocked API client."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = PlannerAgent(api_key="test-key", max_iterations=10)
        return agent

    @pytest.mark.asyncio
    async def test_single_turn_no_tools(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent returns immediately when Claude doesn't use tools.

        Since generate_plan() now validates output, a plan with no tool calls
        will fail validation (compute_training_stress and
        validate_progression_constraints are mandatory).
        """
        mock_response = make_end_turn_response("Here is a plan with no tool calls.")
        mock_agent._transport.create_message = AsyncMock(return_value=mock_response)

        result = await mock_agent.generate_plan(sample_athlete)

        assert result.plan_text == "Here is a plan with no tool calls."
        assert result.iterations == 1
        assert len(result.tool_calls) == 0
        # Validation catches missing mandatory tool calls
        assert result.validation is not None
        assert not result.validation.passed
        assert result.error is not None
        assert "validation failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_tool_use_then_end_turn(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent executes tool calls and returns the final response."""
        # First call: Claude wants to use compute_training_stress
        tool_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {
                "workout_type": "easy",
                "duration_minutes": 45.0,
                "intensity": 0.6,
            },
        }])

        # Second call: Claude returns the final plan
        final_response = make_end_turn_response(
            "# Training Plan\nWeek 1: Easy run, TSS=27.0"
        )

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        result = await mock_agent.generate_plan(sample_athlete)

        assert result.iterations == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "compute_training_stress"
        assert result.tool_calls[0]["success"] is True
        assert "tss" in result.tool_calls[0]["output"]
        # Validation catches missing validate_progression_constraints call
        assert result.validation is not None
        assert not result.validation.passed
        assert result.error is not None
        assert "validate_progression_constraints" in result.error

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_turn(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent handles multiple tool calls in a single response."""
        tool_response = make_tool_use_response([
            {
                "name": "compute_training_stress",
                "input": {
                    "workout_type": "easy",
                    "duration_minutes": 45.0,
                    "intensity": 0.5,
                },
                "id": "toolu_0001",
            },
            {
                "name": "compute_training_stress",
                "input": {
                    "workout_type": "tempo",
                    "duration_minutes": 35.0,
                    "intensity": 0.8,
                },
                "id": "toolu_0002",
            },
        ])

        final_response = make_end_turn_response("Plan with two workouts computed.")

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        result = await mock_agent.generate_plan(sample_athlete)

        assert len(result.tool_calls) == 2
        assert all(tc["success"] for tc in result.tool_calls)

    @pytest.mark.asyncio
    async def test_tool_call_with_validation(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent calls both stress and validation tools."""
        # Turn 1: compute stress
        stress_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {
                "workout_type": "easy",
                "duration_minutes": 45.0,
                "intensity": 0.5,
            },
        }])

        # Turn 2: validate progression
        validate_response = make_tool_use_response([{
            "name": "validate_progression_constraints",
            "input": {
                "weekly_loads": [100.0, 105.0, 108.0, 112.0],
                "risk_tolerance": "moderate",
            },
        }])

        # Turn 3: final plan
        final_response = make_end_turn_response("Plan validated and ready.")

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[stress_response, validate_response, final_response]
        )

        result = await mock_agent.generate_plan(sample_athlete)

        assert result.iterations == 3
        tool_names = [tc["name"] for tc in result.tool_calls]
        assert "compute_training_stress" in tool_names
        assert "validate_progression_constraints" in tool_names

    @pytest.mark.asyncio
    async def test_max_iterations_cap(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent stops after max_iterations and returns an error."""
        # Every response asks for more tool calls (infinite loop scenario)
        infinite_tool_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {
                "workout_type": "easy",
                "duration_minutes": 30.0,
                "intensity": 0.5,
            },
        }])

        mock_agent._transport.create_message = AsyncMock(
            return_value=infinite_tool_response
        )
        mock_agent._max_iterations = 3

        result = await mock_agent.generate_plan(sample_athlete)

        assert result.iterations == 3
        assert result.error is not None
        assert "3 iterations" in result.error

    @pytest.mark.asyncio
    async def test_unknown_tool_handled_gracefully(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent handles unknown tool calls without crashing."""
        tool_response = make_tool_use_response([{
            "name": "nonexistent_tool",
            "input": {"foo": "bar"},
        }])

        final_response = make_end_turn_response("Plan despite tool error.")

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        result = await mock_agent.generate_plan(sample_athlete)

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["success"] is False
        assert "Unknown tool" in result.tool_calls[0]["output"]["error"]

    @pytest.mark.asyncio
    async def test_token_tracking(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent accumulates token usage across iterations."""
        tool_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {
                "workout_type": "easy",
                "duration_minutes": 30.0,
                "intensity": 0.5,
            },
        }])
        final_response = make_end_turn_response("Done.")

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        result = await mock_agent.generate_plan(sample_athlete)

        # Each mock response has 100 input + 200 output tokens
        assert result.total_input_tokens == 200  # 2 iterations
        assert result.total_output_tokens == 400

    @pytest.mark.asyncio
    async def test_tool_results_sent_in_correct_format(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Verify tool_result blocks are sent back with correct structure.

        The Anthropic API expects tool results as a user message containing
        tool_result blocks with tool_use_id, content (JSON string), and
        is_error fields.
        """
        tool_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {
                "workout_type": "easy",
                "duration_minutes": 45.0,
                "intensity": 0.6,
            },
            "id": "toolu_test_123",
        }])
        final_response = make_end_turn_response("Done.")

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        await mock_agent.generate_plan(sample_athlete)

        # The second call should include tool results from the first
        assert mock_agent._transport.create_message.call_count == 2
        second_call_args = mock_agent._transport.create_message.call_args_list[1]
        messages = second_call_args.kwargs["messages"]

        # Messages: [user, assistant (tool_use), user (tool_results)]
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

        # The third message should be tool results
        tool_result_msg = messages[2]
        assert tool_result_msg["role"] == "user"
        result_blocks = tool_result_msg["content"]
        assert len(result_blocks) == 1

        block = result_blocks[0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_test_123"
        assert isinstance(block["content"], str)  # JSON string
        assert block["is_error"] is False

        # Content should be valid JSON with TSS data
        parsed = json.loads(block["content"])
        assert "tss" in parsed

    @pytest.mark.asyncio
    async def test_error_path_has_validation(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Error-path PlannerResults should have validation != None."""
        import anthropic

        mock_agent._transport.create_message = AsyncMock(
            side_effect=anthropic.APIError(
                message="Test error",
                request=MagicMock(),
                body=None,
            )
        )

        result = await mock_agent.generate_plan(sample_athlete)

        assert result.error is not None
        assert result.validation is not None
        assert result.validation.passed is False

    @pytest.mark.asyncio
    async def test_unexpected_stop_reason(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """Agent handles unexpected stop reasons (e.g., max_tokens)."""
        response = MockResponse(
            content=[MockContentBlock(type="text", text="Partial plan...")],
            stop_reason="max_tokens",
            usage=MockUsage(),
        )

        mock_agent._transport.create_message = AsyncMock(return_value=response)

        result = await mock_agent.generate_plan(sample_athlete)

        assert result.plan_text == "Partial plan..."
        assert result.error is not None
        assert "max_tokens" in result.error


# ---------------------------------------------------------------------------
# Tests: Output validation
# ---------------------------------------------------------------------------

class TestOutputValidation:
    """Test validate_plan_output() catches missing tool usage."""

    def test_valid_output_passes(self) -> None:
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}, "success": True},
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Here is a plan.", tool_calls)
        assert result.passed is True
        assert result.issues == []

    def test_empty_text_fails(self) -> None:
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}, "success": True},
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("", tool_calls)
        assert result.passed is False
        assert any("empty" in i.lower() for i in result.issues)

    def test_no_stress_call_passes(self) -> None:
        """compute_training_stress is no longer required — TSS is computed post-hoc."""
        tool_calls = [
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is True

    def test_no_validation_call_fails(self) -> None:
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is False
        assert any("validate_progression_constraints" in i for i in result.issues)

    def test_failed_tool_call_fails(self) -> None:
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}, "success": True},
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": False},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is False
        assert any("failed" in i.lower() for i in result.issues)

    def test_no_tool_calls_fails(self) -> None:
        result = validate_plan_output("Plan text.", [])
        assert result.passed is False
        assert len(result.issues) == 1  # missing validate_progression_constraints

    def test_extra_tools_dont_cause_failure(self) -> None:
        """Extra tool calls beyond the required ones are fine."""
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}, "success": True},
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": True},
            {"name": "simulate_race_outcomes", "input": {}, "output": {}, "success": True},
            {"name": "evaluate_fatigue_state", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Full plan.", tool_calls)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Tests: System prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    """Verify the planner system prompt has the required content."""

    def test_prompt_is_non_empty(self) -> None:
        assert len(PLANNER_SYSTEM_PROMPT) > 100

    def test_prompt_forbids_direct_metrics(self) -> None:
        assert "NEVER generate" in PLANNER_SYSTEM_PROMPT or "NEVER" in PLANNER_SYSTEM_PROMPT

    def test_prompt_mentions_all_tools(self) -> None:
        for tool in [
            "compute_training_stress",
            "validate_progression_constraints",
            "simulate_race_outcomes",
            "evaluate_fatigue_state",
            "reallocate_week_load",
            "project_taper",
        ]:
            assert tool in PLANNER_SYSTEM_PROMPT

    def test_prompt_mentions_safety(self) -> None:
        assert "safety" in PLANNER_SYSTEM_PROMPT.lower() or "safe" in PLANNER_SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# Tests: User message building
# ---------------------------------------------------------------------------

class TestUserMessageBuilding:
    """Test the _build_user_message static method."""

    def test_message_contains_athlete_name(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_user_message(sample_athlete)
        assert sample_athlete.name in msg

    def test_message_contains_goal_distance(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_user_message(sample_athlete)
        assert sample_athlete.goal_distance in msg

    def test_message_contains_json_profile(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_user_message(sample_athlete)
        assert "```json" in msg

    def test_message_mentions_tools(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_user_message(sample_athlete)
        assert "compute_training_stress" in msg

    def test_message_includes_vdot_when_set(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_user_message(sample_athlete)
        assert "VDOT" in msg or "vdot" in msg

    def test_message_includes_injury_when_set(self) -> None:
        athlete = AthleteProfile(
            name="Injured Runner",
            age=35,
            weekly_mileage_base=40.0,
            goal_distance="10K",
            injury_history="Plantar fasciitis 2025",
        )
        msg = PlannerAgent._build_user_message(athlete)
        assert "Plantar fasciitis" in msg


# ---------------------------------------------------------------------------
# Tests: CLI example profiles
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: Plan revision
# ---------------------------------------------------------------------------

class TestPlanRevision:
    """Test revise_plan() and _build_revision_message()."""

    @pytest.fixture
    def mock_agent(self) -> PlannerAgent:
        """Create a PlannerAgent with a mocked API client."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = PlannerAgent(api_key="test-key", max_iterations=10)
        return agent

    def test_revision_message_contains_critique(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_revision_message(
            sample_athlete,
            "Old plan text here.",
            "Safety score too low.",
            ["No rest days in week 3", "ACWR exceeds 1.3"],
        )
        assert "REJECTED" in msg
        assert "Safety score too low." in msg
        assert "No rest days in week 3" in msg
        assert "ACWR exceeds 1.3" in msg

    def test_revision_message_contains_athlete_profile(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_revision_message(
            sample_athlete, "plan", "critique", ["issue"],
        )
        assert sample_athlete.name in msg
        assert "```json" in msg

    def test_revision_message_contains_prior_plan(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_revision_message(
            sample_athlete, "UNIQUE_PLAN_CONTENT_XYZ", "critique", [],
        )
        assert "UNIQUE_PLAN_CONTENT_XYZ" in msg

    def test_revision_message_empty_issues(self, sample_athlete: AthleteProfile) -> None:
        msg = PlannerAgent._build_revision_message(
            sample_athlete, "plan", "critique", [],
        )
        assert "(no specific issues listed)" in msg

    @pytest.mark.asyncio
    async def test_revise_plan_runs_agent_loop(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """revise_plan() goes through the same agent loop as generate_plan()."""
        # Turn 1: tool call
        tool_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {"workout_type": "easy", "duration_minutes": 45.0, "intensity": 0.6},
        }])
        # Turn 2: validation + final
        validate_response = make_tool_use_response([{
            "name": "validate_progression_constraints",
            "input": {"weekly_loads": [100, 105, 108, 112], "risk_tolerance": "moderate"},
        }])
        final_response = make_end_turn_response("Revised plan with fixes.")

        mock_agent._transport.create_message = AsyncMock(
            side_effect=[tool_response, validate_response, final_response]
        )

        result = await mock_agent.revise_plan(
            sample_athlete,
            "Old plan",
            "Needs more rest days.",
            ["Add rest day to week 3"],
        )

        assert result.iterations == 3
        assert result.plan_text == "Revised plan with fixes."
        tool_names = [tc["name"] for tc in result.tool_calls]
        assert "compute_training_stress" in tool_names
        assert "validate_progression_constraints" in tool_names

    @pytest.mark.asyncio
    async def test_revise_plan_validates_output(
        self, mock_agent: PlannerAgent, sample_athlete: AthleteProfile,
    ) -> None:
        """revise_plan() runs validation on the revised output."""
        # No tool calls -> validation will fail
        final_response = make_end_turn_response("Revised plan without tools.")
        mock_agent._transport.create_message = AsyncMock(return_value=final_response)

        result = await mock_agent.revise_plan(
            sample_athlete, "Old plan", "Critique.", ["Issue"],
        )

        assert result.validation is not None
        assert not result.validation.passed
        assert result.error is not None


class TestCLIExampleProfiles:
    """Verify built-in CLI example profiles are valid AthleteProfiles."""

    @pytest.mark.parametrize("name", ["beginner", "intermediate", "advanced", "aggressive"])
    def test_example_profile_validates(self, name: str) -> None:
        from src.cli import EXAMPLE_PROFILES
        profile = AthleteProfile.model_validate(EXAMPLE_PROFILES[name])
        assert profile.name
        assert profile.goal_distance
