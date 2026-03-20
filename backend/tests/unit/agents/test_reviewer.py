"""Unit tests for ReviewerAgent.

Covers constructor behaviour, property accessors, _parse_review_verdict (the
most logic-dense static method), _build_review_message, and review_plan()
with a mock transport including approved, rejected, and error paths.

WHY unit tests separate from integration tests:
- _parse_review_verdict has many edge cases (fallback scanning, non-boolean
  approved, missing score keys, invalid types) that integration tests skip.
- Constructor tests verify api_key/transport wiring once without full loops.
- Message-building tests pin the prompt contract without API calls.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from src.agents.reviewer import ReviewerAgent, ReviewerResult
from src.agents.transport import MessageTransport
from src.models.athlete import AthleteProfile, RiskTolerance
from src.models.decision_log import ReviewerScores
from src.tools.registry import ToolRegistry
from tests.helpers import (
    MockContentBlock,
    MockResponse,
    MockUsage,
    make_end_turn_response,
    make_tool_use_response,
    make_verdict_response,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_athlete() -> AthleteProfile:
    """Standard athlete profile used across reviewer unit tests."""
    return AthleteProfile(
        name="Review Test Runner",
        age=32,
        weekly_mileage_base=50.0,
        goal_distance="Half Marathon",
        goal_time_minutes=105.0,
        vdot=45.0,
        risk_tolerance=RiskTolerance.MODERATE,
        training_days_per_week=5,
    )


VALID_PLAN_TEXT = """\
# 12-Week Half Marathon Plan

```json
{"athlete_name": "Review Test Runner", "weeks": [{"week": 1, "load": 100}]}
```
"""

SAMPLE_TOOL_CALLS = [
    {"name": "compute_training_stress", "input": {}, "output": {"tss": 35.0}, "success": True},
    {"name": "validate_progression_constraints", "input": {}, "output": {"valid": True}, "success": True},
]


@pytest.fixture
def reviewer_with_mock_transport() -> ReviewerAgent:
    """ReviewerAgent backed by a stub transport (no real API key required)."""

    class StubTransport:
        async def create_message(self, **kwargs: Any) -> Any:  # noqa: ARG002
            raise NotImplementedError("Override create_message in each test.")

    return ReviewerAgent(transport=StubTransport())


# ---------------------------------------------------------------------------
# Tests: Constructor
# ---------------------------------------------------------------------------


class TestReviewerConstructor:
    """Verify ReviewerAgent.__init__() wiring and validation."""

    def test_api_key_kwarg_accepted(self) -> None:
        """Explicit api_key creates an AnthropicTransport."""
        with patch("src.agents.reviewer.AnthropicTransport") as mock_cls:
            ReviewerAgent(api_key="sk-reviewer-key")
            mock_cls.assert_called_once_with(api_key="sk-reviewer-key")

    def test_api_key_falls_back_to_env(self) -> None:
        """When api_key is None, ANTHROPIC_API_KEY env var is used."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-reviewer"}):
            with patch("src.agents.reviewer.AnthropicTransport") as mock_cls:
                ReviewerAgent()
                mock_cls.assert_called_once_with(api_key="sk-env-reviewer")

    def test_no_key_no_transport_raises(self) -> None:
        """ValueError raised when neither api_key nor transport are provided."""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="No API key provided"):
                ReviewerAgent()

    def test_transport_overrides_api_key(self) -> None:
        """When transport is provided, api_key and env var are ignored."""

        class DummyTransport:
            async def create_message(self, **_: Any) -> Any:
                raise NotImplementedError

        transport = DummyTransport()
        with patch("src.agents.reviewer.AnthropicTransport") as mock_cls:
            agent = ReviewerAgent(api_key="should-be-ignored", transport=transport)
            mock_cls.assert_not_called()
        assert agent._transport is transport

    def test_default_model_is_opus(self) -> None:
        """Default model is claude-opus-4-20250514 (safety-critical reviewer)."""
        agent = ReviewerAgent(api_key="sk-test")
        assert "opus" in agent.model.lower()

    def test_custom_model_stored(self) -> None:
        """Custom model argument is preserved."""
        agent = ReviewerAgent(api_key="sk-test", model="claude-test-reviewer")
        assert agent.model == "claude-test-reviewer"

    def test_default_max_iterations(self) -> None:
        """Default max_iterations for reviewer is 10."""
        agent = ReviewerAgent(api_key="sk-test")
        assert agent._max_iterations == 10

    def test_custom_max_iterations(self) -> None:
        """Custom max_iterations is stored."""
        agent = ReviewerAgent(api_key="sk-test", max_iterations=5)
        assert agent._max_iterations == 5


# ---------------------------------------------------------------------------
# Tests: Properties
# ---------------------------------------------------------------------------


class TestReviewerProperties:
    """Verify model and registry property accessors."""

    def test_model_property_returns_model_string(self) -> None:
        """model property returns the stored model identifier string."""
        agent = ReviewerAgent(api_key="sk-test", model="claude-reviewer-model")
        assert agent.model == "claude-reviewer-model"

    def test_registry_property_returns_tool_registry(self) -> None:
        """registry property returns a ToolRegistry instance."""
        agent = ReviewerAgent(api_key="sk-test")
        assert isinstance(agent.registry, ToolRegistry)

    def test_registry_has_five_tools(self) -> None:
        """Built registry contains all 6 tools."""
        agent = ReviewerAgent(api_key="sk-test")
        assert len(agent.registry.tool_names) == 6


# ---------------------------------------------------------------------------
# Tests: _parse_review_verdict
# ---------------------------------------------------------------------------


class TestParseReviewVerdict:
    """Exhaustively test _parse_review_verdict() edge cases.

    WHY: This is the most complex static method in the codebase. It handles
    two JSON extraction strategies (fenced block + fallback brace scanning),
    strict boolean-only approved semantics, missing/invalid score keys, and
    issues coercion. Each case is tested independently for clear failure signals.
    """

    # --- Happy-path approved ---

    def test_valid_fenced_block_approved(self) -> None:
        """Fenced ```json block with approved=true is parsed correctly.

        WHY: Primary code path for well-behaved Claude responses.
        """
        text = (
            '```json\n'
            '{"approved": true, "scores": {"safety": 85, "progression": 80, '
            '"specificity": 90, "feasibility": 75}, "critique": "Good.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is True
        assert result.scores is not None
        assert result.scores.safety == 85
        assert result.scores.progression == 80
        assert result.scores.specificity == 90
        assert result.scores.feasibility == 75
        assert result.critique == "Good."
        assert result.issues == []
        assert result.error is None

    def test_valid_fenced_block_rejected(self) -> None:
        """Fenced block with approved=false and issues is parsed correctly."""
        text = (
            '```json\n'
            '{"approved": false, "scores": {"safety": 55, "progression": 80, '
            '"specificity": 85, "feasibility": 75}, "critique": "Too risky.", '
            '"issues": ["No rest days in week 3", "ACWR exceeds 1.3"]}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 55
        assert result.critique == "Too risky."
        assert result.issues == ["No rest days in week 3", "ACWR exceeds 1.3"]
        assert result.error is None

    def test_overall_score_computation(self) -> None:
        """ReviewerScores.overall applies safety 2x weight correctly.

        WHY: The weighted overall score drives orchestrator approval logic.
        If the formula drifts, plans with unsafe scores could get approved.
        """
        text = (
            '```json\n'
            '{"approved": true, "scores": {"safety": 80, "progression": 70, '
            '"specificity": 90, "feasibility": 80}, "critique": "OK.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.scores is not None
        # (80*2 + 70 + 90 + 80) / 5 = 400/5 = 80.0
        assert result.scores.overall == pytest.approx(80.0)

    # --- Fallback brace-scanning ---

    def test_fallback_to_inline_json(self) -> None:
        """When no fenced block, inline JSON with 'approved' is found by rfind.

        WHY: Claude may omit the fenced block and emit raw JSON. The fallback
        scanner must find it via balanced-brace matching.
        """
        text = (
            'My verdict is {"approved": false, "scores": {"safety": 50, '
            '"progression": 50, "specificity": 50, "feasibility": 50}, '
            '"critique": "Bad.", "issues": ["Unsafe load spike"]}'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 50
        assert result.issues == ["Unsafe load spike"]

    def test_rfind_picks_last_approved_occurrence(self) -> None:
        """rfind selects the last 'approved' keyword so the verdict wins over quoted text.

        WHY: The reviewer may quote the plan text (which could contain 'approved')
        before emitting the verdict. The last occurrence is always the verdict.
        """
        text = (
            'The plan says {"approved": true, "note": "planner approved"} but I disagree. '
            'Verdict: {"approved": false, "scores": {"safety": 40, "progression": 60, '
            '"specificity": 70, "feasibility": 60}, "critique": "Unsafe.", "issues": ["Bad"]}'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 40

    # --- Missing / absent JSON ---

    def test_no_json_block_at_all(self) -> None:
        """No JSON in the response returns a rejected result with an error.

        WHY: Claude might return prose without JSON. The parser must degrade
        gracefully rather than crashing.
        """
        result = ReviewerAgent._parse_review_verdict("No JSON here at all.")
        assert result.approved is False
        assert result.error is not None
        assert "Could not find JSON" in result.error

    def test_empty_text_returns_error(self) -> None:
        """Empty response string returns a rejected result with an error.

        WHY: Empty responses occur on timeout or silent API failures.
        """
        result = ReviewerAgent._parse_review_verdict("")
        assert result.approved is False
        assert result.error is not None

    def test_malformed_json_in_fenced_block(self) -> None:
        """Syntactically invalid JSON in a fenced block returns a parse error.

        WHY: If Claude truncates its JSON output, we must report the parse
        failure rather than silently approving or crashing.
        """
        text = '```json\n{approved: true, broken json}\n```'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.error is not None
        assert "Invalid JSON" in result.error

    # --- Missing 'approved' key ---

    def test_missing_approved_key_no_fallback_scan(self) -> None:
        """JSON without 'approved' key has rfind return -1, triggering error.

        WHY: rfind('"approved"') is the trigger for fallback scanning.
        A JSON blob without 'approved' cannot be parsed as a verdict.
        """
        # No fenced block, and no "approved" key in inline JSON
        text = '{"scores": {"safety": 80}, "critique": "Fine."}'
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.error is not None

    # --- Non-boolean approved ---

    def test_string_true_not_approved(self) -> None:
        """approved='true' (string) is treated as rejected, not approved.

        WHY: Only Python boolean True passes the `raw_approved is True` check.
        String coercion would be a security/safety vulnerability.
        """
        text = (
            '```json\n'
            '{"approved": "true", "scores": {"safety": 90, "progression": 85, '
            '"specificity": 80, "feasibility": 80}, "critique": "Good.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False

    def test_integer_one_not_approved(self) -> None:
        """approved=1 (integer) is treated as rejected.

        WHY: Same as above — truthy int is not boolean True.
        """
        text = (
            '```json\n'
            '{"approved": 1, "scores": {"safety": 90, "progression": 85, '
            '"specificity": 80, "feasibility": 80}, "critique": "Good.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False

    def test_null_approved_not_approved(self) -> None:
        """approved=null is treated as rejected."""
        text = (
            '```json\n'
            '{"approved": null, "scores": {"safety": 90, "progression": 85, '
            '"specificity": 80, "feasibility": 80}, "critique": "Good.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False

    # --- Score key validation ---

    def test_missing_score_keys_returns_error(self) -> None:
        """Only 3 of 4 required score keys triggers a 'Missing score keys' error.

        WHY: All four dimensions (safety, progression, specificity, feasibility)
        are required for weighted scoring. Partial scores break the formula.
        """
        text = (
            '```json\n'
            '{"approved": true, "scores": {"safety": 90, "progression": 85, '
            '"specificity": 80}, "critique": "Good.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.error is not None
        assert "Missing score keys" in result.error
        assert "feasibility" in result.error

    def test_invalid_score_type_returns_error(self) -> None:
        """Non-numeric score values trigger an 'Invalid scores' error.

        WHY: int() conversion of strings like 'high' would raise TypeError/ValueError.
        The parser must catch this and surface it rather than crashing.
        """
        text = (
            '```json\n'
            '{"approved": true, "scores": {"safety": "high", "progression": 80, '
            '"specificity": 80, "feasibility": 80}, "critique": "Good.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is False
        assert result.error is not None
        assert "Invalid scores" in result.error

    def test_missing_scores_key_entirely(self) -> None:
        """When 'scores' key is absent, scores is None and no error is raised.

        WHY: Scores are optional in the data model. A missing scores dict should
        not block the verdict — it's a degraded-but-valid state.
        """
        text = (
            '```json\n'
            '{"approved": true, "critique": "Fine.", "issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.approved is True
        assert result.scores is None
        assert result.error is None

    # --- Issues coercion ---

    def test_issues_coerced_to_strings(self) -> None:
        """Non-string issues are coerced to str; None values are filtered out.

        WHY: The issues list must be List[str] for downstream formatting.
        Integers and nulls from Claude output must be handled gracefully.
        """
        text = (
            '```json\n'
            '{"approved": false, "scores": {"safety": 50, "progression": 50, '
            '"specificity": 50, "feasibility": 50}, "critique": "Bad.", '
            '"issues": [1, "real issue", null, 2.5]}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.issues == ["1", "real issue", "2.5"]

    def test_empty_issues_list(self) -> None:
        """Empty issues list is preserved as-is."""
        text = (
            '```json\n'
            '{"approved": true, "scores": {"safety": 85, "progression": 80, '
            '"specificity": 80, "feasibility": 80}, "critique": "All good.", '
            '"issues": []}\n'
            '```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.issues == []

    def test_critique_included_in_result(self) -> None:
        """Critique text is passed through to the ReviewerResult."""
        critique = "The plan lacks adequate recovery weeks."
        text = (
            f'```json\n'
            f'{{"approved": false, "scores": {{"safety": 65, "progression": 70, '
            f'"specificity": 75, "feasibility": 70}}, "critique": "{critique}", '
            f'"issues": ["Add deload week"]}}\n'
            f'```'
        )
        result = ReviewerAgent._parse_review_verdict(text)
        assert result.critique == critique


# ---------------------------------------------------------------------------
# Tests: _build_review_message
# ---------------------------------------------------------------------------


class TestBuildReviewMessage:
    """Pin the contract for _build_review_message() static method.

    WHY: The review message is the reviewer's full context. Missing profile
    data or tool summaries degrade review quality silently.
    """

    def test_contains_athlete_name(self, sample_athlete: AthleteProfile) -> None:
        """Athlete name is present for the reviewer to reference."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert sample_athlete.name in msg

    def test_contains_profile_json_block(self, sample_athlete: AthleteProfile) -> None:
        """Athlete profile is serialized into a fenced JSON block."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "```json" in msg

    def test_contains_plan_text(self, sample_athlete: AthleteProfile) -> None:
        """The plan under review appears verbatim in the message."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "12-Week Half Marathon Plan" in msg

    def test_contains_tool_summary_with_status(self, sample_athlete: AthleteProfile) -> None:
        """Tool summary lists each tool call with OK/FAIL status.

        WHY: Reviewer uses this to detect which claims are tool-backed vs fabricated.
        """
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "compute_training_stress [OK]" in msg
        assert "validate_progression_constraints [OK]" in msg

    def test_tool_call_count_mentioned(self, sample_athlete: AthleteProfile) -> None:
        """The count of planner tool calls is stated explicitly."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "2 tool call(s)" in msg

    def test_empty_tool_calls_shows_none(self, sample_athlete: AthleteProfile) -> None:
        """Zero tool calls produces '0 tool call(s)' and '(none)' summary."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, [],
        )
        assert "0 tool call(s)" in msg
        assert "(none)" in msg

    def test_failed_tool_shown_as_fail(self, sample_athlete: AthleteProfile) -> None:
        """A failed tool call is marked [FAIL] in the summary."""
        tool_calls = [
            {"name": "simulate_race_outcomes", "input": {}, "output": {}, "success": False},
        ]
        msg = ReviewerAgent._build_review_message(sample_athlete, VALID_PLAN_TEXT, tool_calls)
        assert "simulate_race_outcomes [FAIL]" in msg

    def test_contains_scoring_instructions(self, sample_athlete: AthleteProfile) -> None:
        """Message asks reviewer to score each dimension 0-100."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "safety" in msg.lower()
        assert "progression" in msg.lower()
        assert "specificity" in msg.lower()
        assert "feasibility" in msg.lower()

    def test_contains_pass_threshold_reference(self, sample_athlete: AthleteProfile) -> None:
        """Message mentions the numeric rejection threshold (70)."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "70" in msg

    def test_requests_json_verdict_block(self, sample_athlete: AthleteProfile) -> None:
        """Message instructs reviewer to return verdict as a ```json block."""
        msg = ReviewerAgent._build_review_message(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )
        assert "```json" in msg


# ---------------------------------------------------------------------------
# Tests: review_plan with mock transport
# ---------------------------------------------------------------------------


class TestReviewPlan:
    """Test review_plan() end-to-end with a mocked transport.

    WHY: These tests exercise the full _run_agent_loop + _parse_review_verdict
    pipeline, verifying that iteration counts, token accumulation, tool dispatch,
    and error handling all wire together correctly.
    """

    @pytest.mark.asyncio
    async def test_approved_verdict_single_turn(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer approves in a single turn with no tool calls.

        WHY: Happy path — reviewer looks at the plan and immediately approves.
        """
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            return_value=make_verdict_response(
                approved=True,
                scores={"safety": 90, "progression": 85, "specificity": 80, "feasibility": 75},
                critique="Solid plan.",
            )
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is True
        assert result.scores is not None
        assert result.scores.safety == 90
        assert result.iterations == 1
        assert len(result.tool_calls) == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_rejected_verdict_with_issues(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer rejects with specific issues and critique.

        WHY: Rejected verdicts must carry issues back to the planner for revision.
        """
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            return_value=make_verdict_response(
                approved=False,
                scores={"safety": 55, "progression": 80, "specificity": 85, "feasibility": 75},
                critique="Safety concerns detected.",
                issues=["Week 3 has no rest day", "ACWR exceeds 1.3 in week 5"],
            )
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is False
        assert result.scores is not None
        assert result.scores.safety == 55
        assert result.critique == "Safety concerns detected."
        assert len(result.issues) == 2
        assert "Week 3 has no rest day" in result.issues

    @pytest.mark.asyncio
    async def test_spot_check_with_tool_use_then_verdict(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer uses a tool to spot-check before returning verdict.

        WHY: Verifies that the reviewer's tool-use loop works identically to
        the planner's — tool call is dispatched, results appended, loop continues.
        """
        tool_response = make_tool_use_response([{
            "name": "compute_training_stress",
            "input": {"workout_type": "easy", "duration_minutes": 45.0, "intensity": 0.6},
        }])
        verdict_response = make_verdict_response(
            approved=True,
            scores={"safety": 88, "progression": 82, "specificity": 85, "feasibility": 80},
        )

        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[tool_response, verdict_response]
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is True
        assert result.iterations == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "compute_training_stress"
        assert result.tool_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_token_accumulation(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Token counts accumulate correctly across iterations.

        WHY: Reviewer token costs feed into the orchestrator's budget tracking.
        Two iterations of default MockUsage (100 in + 200 out each) = 200/400.
        """
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[
                make_tool_use_response([{
                    "name": "validate_progression_constraints",
                    "input": {"weekly_loads": [100, 105, 110], "risk_tolerance": "moderate"},
                }]),
                make_verdict_response(
                    approved=True,
                    scores={"safety": 85, "progression": 80, "specificity": 80, "feasibility": 80},
                ),
            ]
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.total_input_tokens == 200   # 100 per iteration * 2
        assert result.total_output_tokens == 400  # 200 per iteration * 2

    @pytest.mark.asyncio
    async def test_malformed_verdict_returns_error(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Unparseable verdict text returns a rejected result with error.

        WHY: Claude might forget the JSON format. The agent must not crash
        and must surface the parsing failure clearly.
        """
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            return_value=make_end_turn_response(
                "I reviewed the plan and it looks fine. No JSON needed."
            )
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is False
        assert result.error is not None
        assert "Could not find JSON" in result.error

    @pytest.mark.asyncio
    async def test_api_error_captured_in_result(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """anthropic.APIError is caught and surfaces as approved=False with error.

        WHY: Reviewer errors must not crash the orchestrator. A failed review
        should be treated as rejection so the planner can retry.
        """
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            side_effect=anthropic.APIError(
                message="Service unavailable",
                request=MagicMock(),
                body=None,
            )
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is False
        assert result.error is not None
        assert "API error" in result.error

    @pytest.mark.asyncio
    async def test_generic_exception_captured_in_result(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Unexpected exceptions are caught and surfaced without propagating.

        WHY: Bugs in parsing or registry dispatch must not escape to callers.
        """
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            side_effect=ValueError("Unexpected internal error")
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is False
        assert result.error is not None
        assert "ValueError" in result.error

    @pytest.mark.asyncio
    async def test_max_iterations_cap(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Reviewer stops after max_iterations and returns approved=False with error.

        WHY: Mirrors the planner's iteration cap. Prevents runaway reviewer costs.
        """
        reviewer_with_mock_transport._max_iterations = 3
        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            return_value=make_tool_use_response([{
                "name": "compute_training_stress",
                "input": {"workout_type": "easy", "duration_minutes": 30.0, "intensity": 0.5},
            }])
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        assert result.approved is False
        assert result.iterations == 3
        assert result.error is not None
        assert "3 iterations" in result.error

    @pytest.mark.asyncio
    async def test_unexpected_stop_reason_sets_error(
        self,
        reviewer_with_mock_transport: ReviewerAgent,
        sample_athlete: AthleteProfile,
    ) -> None:
        """Unexpected stop_reason triggers error on the result.

        WHY: stop_reason='max_tokens' means the verdict is truncated and
        likely unparseable. The reviewer must set an error rather than
        silently approving a partial response.
        """
        verdict = {
            "approved": True,
            "scores": {"safety": 85, "progression": 80, "specificity": 80, "feasibility": 80},
            "critique": "Good.",
            "issues": [],
        }
        # Deliver valid JSON but with unexpected stop_reason
        truncated_response = MockResponse(
            content=[MockContentBlock(
                type="text",
                text=f"```json\n{json.dumps(verdict)}\n```",
            )],
            stop_reason="max_tokens",
            usage=MockUsage(),
        )

        reviewer_with_mock_transport._transport.create_message = AsyncMock(  # type: ignore[attr-defined]
            return_value=truncated_response
        )

        result = await reviewer_with_mock_transport.review_plan(
            sample_athlete, VALID_PLAN_TEXT, SAMPLE_TOOL_CALLS,
        )

        # The reviewer loop exits on unexpected stop_reason and sets error
        assert result.error is not None
        assert "max_tokens" in result.error
