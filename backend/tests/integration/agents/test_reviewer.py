"""Integration tests for the reviewer agent.

Tests the full reviewer pipeline with a mocked Anthropic API client.
Verifies verdict parsing, tool spot-checking, score handling, and error paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.prompts import REVIEWER_SYSTEM_PROMPT
from src.agents.reviewer import ReviewerAgent
from src.models.athlete import AthleteProfile
from tests.helpers import (
    make_end_turn_response,
    make_tool_use_response,
    make_verdict_response,
)

# sample_athlete fixture is provided by tests/conftest.py


VALID_PLAN_TEXT = """\
# Training Plan for Test Runner

## Macrocycle: 8-week 5K plan

```json
{
  "athlete_name": "Test Runner",
  "goal_event": "5K",
  "weeks": [
    {"week_number": 1, "phase": "base", "target_load": 100, "workouts": []}
  ],
  "predicted_finish_time_minutes": 25.2
}
```
"""

SAMPLE_TOOL_CALLS = [
    {"name": "compute_training_stress", "input": {}, "output": {"tss": 30.0}, "success": True},
    {
        "name": "validate_progression_constraints",
        "input": {},
        "output": {"valid": True},
        "success": True,
    },
]


# ---------------------------------------------------------------------------
# Tests: Verdict parsing
# ---------------------------------------------------------------------------


class TestVerdictParsing:
    """Test _parse_review_verdict() with various input shapes."""

    def test_valid_approved_verdict(self) -> None:
        text = '```json\n{"approved": true, "scores": {"safety": 85, "progression": 80, "specificity": 90, "feasibility": 75}, "critique": "Good plan.", "issues": []}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is True
        assert result.scores is not None
        assert result.scores.safety == 85
        assert result.scores.overall == pytest.approx((85 * 2 + 80 + 90 + 75) / 5)
        assert result.issues == []
        assert result.error is None

    def test_valid_rejected_verdict(self) -> None:
        text = '```json\n{"approved": false, "scores": {"safety": 60, "progression": 80, "specificity": 85, "feasibility": 75}, "critique": "Unsafe.", "issues": ["No rest days"]}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 60
        assert result.issues == ["No rest days"]

    def test_no_json_block(self) -> None:
        result = ReviewerAgent._parse_review_verdict("This has no JSON at all.")
        assert result.approved is False
        assert result.error is not None
        assert "Could not find JSON" in result.error

    def test_malformed_json(self) -> None:
        text = "```json\n{approved: true, broken}\n```"
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_missing_scores(self) -> None:
        text = '```json\n{"approved": true, "critique": "Fine.", "issues": []}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is True
        assert result.scores is None
        assert result.error is None

    def test_fallback_to_inline_json(self) -> None:
        """When no fenced block exists, find inline JSON with 'approved'."""
        text = 'My verdict is {"approved": false, "scores": {"safety": 50, "progression": 50, "specificity": 50, "feasibility": 50}, "critique": "Bad.", "issues": ["Unsafe"]}'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.scores is not None

    def test_empty_text(self) -> None:
        result = ReviewerAgent._parse_review_verdict("")
        assert result.approved is False
        assert result.error is not None

    def test_string_approved_treated_as_rejected(self) -> None:
        """'approved': 'true' (string) must NOT approve — only boolean True passes."""
        text = '```json\n{"approved": "true", "scores": {"safety": 90, "progression": 85, "specificity": 80, "feasibility": 80}, "critique": "Good.", "issues": []}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False

    def test_int_approved_treated_as_rejected(self) -> None:
        """'approved': 1 (int) must NOT approve."""
        text = '```json\n{"approved": 1, "scores": {"safety": 90, "progression": 85, "specificity": 80, "feasibility": 80}, "critique": "Good.", "issues": []}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False

    def test_partial_score_keys_returns_error(self) -> None:
        """Only 3 of 4 required score keys → error result."""
        text = '```json\n{"approved": true, "scores": {"safety": 90, "progression": 85, "specificity": 80}, "critique": "Good.", "issues": []}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.error is not None
        assert "Missing score keys" in result.error
        assert "feasibility" in result.error

    def test_rfind_selects_last_approved_occurrence(self) -> None:
        """When text contains multiple 'approved' keywords, the last one (verdict) is used."""
        # Simulate reviewer quoting the plan's approved field before giving own verdict
        text = (
            'The plan states {"approved": true, "foo": "bar"} but I disagree. '
            'My verdict: {"approved": false, "scores": {"safety": 50, "progression": 60, '
            '"specificity": 70, "feasibility": 60}, "critique": "Unsafe.", "issues": ["Bad"]}'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 50

    def test_issues_coerced_to_strings(self) -> None:
        """Non-string issue values are coerced to strings, None values are filtered."""
        text = '```json\n{"approved": false, "scores": {"safety": 50, "progression": 50, "specificity": 50, "feasibility": 50}, "critique": "Bad.", "issues": [1, "real issue", null]}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.issues == ["1", "real issue"]


# ---------------------------------------------------------------------------
# Tests: Review message building
# ---------------------------------------------------------------------------


class TestReviewMessageBuilding:
    """Test _build_review_message() output."""

    def test_contains_athlete_name(self, sample_athlete: AthleteProfile) -> None:
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )
        assert sample_athlete.name in msg

    def test_contains_plan_text(self, sample_athlete: AthleteProfile) -> None:
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )
        assert "Training Plan for Test Runner" in msg

    def test_contains_tool_summary(self, sample_athlete: AthleteProfile) -> None:
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )
        assert "compute_training_stress [OK]" in msg
        assert "2 tool call(s)" in msg

    def test_empty_tool_calls(self, sample_athlete: AthleteProfile) -> None:
        msg = ReviewerAgent._build_review_message(sample_athlete, VALID_PLAN_TEXT, [])
        assert "0 tool call(s)" in msg
        assert "(none)" in msg

    def test_contains_scoring_instructions(self, sample_athlete: AthleteProfile) -> None:
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )
        assert "safety" in msg.lower()
        assert "progression" in msg.lower()


# ---------------------------------------------------------------------------
# Tests: Agent loop with mocked API
# ---------------------------------------------------------------------------


class TestReviewerAgentLoop:
    """Test the reviewer agent loop with mocked Anthropic client."""

    @pytest.fixture
    def mock_reviewer(self) -> ReviewerAgent:
        """Create a ReviewerAgent with a mocked API client."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = ReviewerAgent(api_key="test-key", max_iterations=10)
        return agent

    @pytest.mark.asyncio
    async def test_approve_without_tools(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer approves immediately without spot-checking."""
        response = make_verdict_response(
            approved=True,
            scores={"safety": 90, "progression": 85, "specificity": 80, "feasibility": 75},
        )
        mock_reviewer._transport.create_message = AsyncMock(return_value=response)

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        assert result.approved is True
        assert result.scores is not None
        assert result.scores.safety == 90
        assert result.iterations == 1
        assert len(result.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_reject_with_issues(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer rejects with specific issues."""
        response = make_verdict_response(
            approved=False,
            scores={"safety": 55, "progression": 80, "specificity": 85, "feasibility": 75},
            critique="Safety concerns: no rest days in week 3.",
            issues=["Week 3 has no rest day", "ACWR exceeds 1.3 in week 5"],
        )
        mock_reviewer._transport.create_message = AsyncMock(return_value=response)

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 55
        assert len(result.issues) == 2

    @pytest.mark.asyncio
    async def test_spot_check_with_tools(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer uses tools to verify claims before scoring."""
        # Turn 1: reviewer spot-checks TSS
        tool_response = make_tool_use_response(
            [
                {
                    "name": "compute_training_stress",
                    "input": {
                        "workout_type": "easy",
                        "duration_minutes": 45.0,
                        "intensity": 0.6,
                    },
                }
            ]
        )
        # Turn 2: verdict
        verdict_response = make_verdict_response(
            approved=True,
            scores={"safety": 88, "progression": 82, "specificity": 85, "feasibility": 80},
        )

        mock_reviewer._transport.create_message = AsyncMock(
            side_effect=[tool_response, verdict_response]
        )

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        assert result.approved is True
        assert result.iterations == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "compute_training_stress"

    @pytest.mark.asyncio
    async def test_token_tracking(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Token usage is accumulated across iterations."""
        tool_response = make_tool_use_response(
            [
                {
                    "name": "validate_progression_constraints",
                    "input": {
                        "weekly_loads": [100, 105, 110, 115],
                        "risk_tolerance": "moderate",
                    },
                }
            ]
        )
        verdict_response = make_verdict_response(
            approved=True,
            scores={"safety": 85, "progression": 80, "specificity": 80, "feasibility": 80},
        )

        mock_reviewer._transport.create_message = AsyncMock(
            side_effect=[tool_response, verdict_response]
        )

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        # Each mock response: 100 input + 200 output (from shared MockUsage)
        assert result.total_input_tokens == 200
        assert result.total_output_tokens == 400

    @pytest.mark.asyncio
    async def test_malformed_verdict_returns_error(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Malformed verdict text returns a rejected result with error."""
        response = make_end_turn_response("I don't know how to format JSON.")
        mock_reviewer._transport.create_message = AsyncMock(return_value=response)

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        assert result.approved is False
        assert result.error is not None
        assert "Could not find JSON" in result.error

    @pytest.mark.asyncio
    async def test_max_iterations_cap(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer stops after max_iterations."""
        infinite_tool_response = make_tool_use_response(
            [
                {
                    "name": "compute_training_stress",
                    "input": {"workout_type": "easy", "duration_minutes": 30.0, "intensity": 0.5},
                }
            ]
        )

        mock_reviewer._transport.create_message = AsyncMock(return_value=infinite_tool_response)
        mock_reviewer._max_iterations = 3

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        assert result.approved is False
        assert result.iterations == 3
        assert result.error is not None
        assert "3 iterations" in result.error

    @pytest.mark.asyncio
    async def test_api_error_handled(
        self,
        mock_reviewer: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """API errors produce a rejected result with error message."""
        from unittest.mock import MagicMock

        import anthropic

        mock_reviewer._transport.create_message = AsyncMock(
            side_effect=anthropic.APIError(
                message="Rate limited",
                request=MagicMock(),
                body=None,
            )
        )

        result = await mock_reviewer.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS
        )

        assert result.approved is False
        assert result.error is not None
        assert "API error" in result.error


# ---------------------------------------------------------------------------
# Tests: System prompt
# ---------------------------------------------------------------------------


class TestReviewerSystemPrompt:
    """Verify the reviewer system prompt has required content."""

    def test_prompt_is_non_empty(self) -> None:
        assert len(REVIEWER_SYSTEM_PROMPT) > 100

    def test_prompt_mentions_four_dimensions(self) -> None:
        for dim in ["safety", "progression", "specificity", "feasibility"]:
            assert dim.lower() in REVIEWER_SYSTEM_PROMPT.lower()

    def test_prompt_forbids_direct_metrics(self) -> None:
        assert "NEVER" in REVIEWER_SYSTEM_PROMPT

    def test_prompt_mentions_tools(self) -> None:
        for tool in [
            "compute_training_stress",
            "validate_progression_constraints",
            "evaluate_fatigue_state",
            "simulate_race_outcomes",
            "reallocate_week_load",
            "project_taper",
        ]:
            assert tool in REVIEWER_SYSTEM_PROMPT

    def test_prompt_requires_json_verdict(self) -> None:
        assert "```json" in REVIEWER_SYSTEM_PROMPT
        assert '"approved"' in REVIEWER_SYSTEM_PROMPT

    def test_prompt_mentions_scoring(self) -> None:
        assert "0-100" in REVIEWER_SYSTEM_PROMPT
        assert "70" in REVIEWER_SYSTEM_PROMPT

    def test_prompt_mentions_safety_weight(self) -> None:
        assert "2x" in REVIEWER_SYSTEM_PROMPT.lower()
