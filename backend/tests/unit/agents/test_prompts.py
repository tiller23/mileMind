"""Tests for system prompt constants in src/agents/prompts.py.

Verifies that PLANNER_SYSTEM_PROMPT and REVIEWER_SYSTEM_PROMPT:
- Are non-empty strings
- Contain all required structural sections
- Reference all 6 registered tool names
- Forbid direct metric generation via explicit NEVER directives
- Have the REVIEW_PASS_THRESHOLD substituted (no raw placeholder)
- Contain the expected 4 scoring dimensions and safety weighting
"""

from __future__ import annotations

import pytest

from src.agents.prompts import PLANNER_SYSTEM_PROMPT, REVIEWER_SYSTEM_PROMPT
from src.models.decision_log import REVIEW_PASS_THRESHOLD


# ---------------------------------------------------------------------------
# Tool names that must appear in both prompts
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = [
    "compute_training_stress",
    "evaluate_fatigue_state",
    "validate_progression_constraints",
    "simulate_race_outcomes",
    "reallocate_week_load",
    "project_taper",
]


# ---------------------------------------------------------------------------
# PLANNER_SYSTEM_PROMPT tests
# ---------------------------------------------------------------------------


class TestPlannerSystemPrompt:
    """Tests for PLANNER_SYSTEM_PROMPT content and structure."""

    def test_is_non_empty_string(self) -> None:
        """PLANNER_SYSTEM_PROMPT must be a non-empty string."""
        assert isinstance(PLANNER_SYSTEM_PROMPT, str)
        assert len(PLANNER_SYSTEM_PROMPT) > 0

    @pytest.mark.parametrize("section", [
        "CRITICAL CONSTRAINTS",
        "AVAILABLE TOOLS",
        "PLANNING WORKFLOW",
        "OUTPUT FORMAT",
        "SAFETY RULES",
        "EFFICIENCY",
    ])
    def test_contains_required_section(self, section: str) -> None:
        """PLANNER_SYSTEM_PROMPT must contain every structural section header.

        Each section guides the LLM through its responsibilities; a missing
        section means the prompt is incomplete and the agent may skip steps.
        """
        assert section in PLANNER_SYSTEM_PROMPT, (
            f"PLANNER_SYSTEM_PROMPT is missing section: {section!r}"
        )

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
    def test_mentions_all_tool_names(self, tool_name: str) -> None:
        """PLANNER_SYSTEM_PROMPT must name every available tool.

        If a tool is omitted the planner may never discover it exists,
        leading to free-generated numbers instead of tool calls.
        """
        assert tool_name in PLANNER_SYSTEM_PROMPT, (
            f"PLANNER_SYSTEM_PROMPT does not mention tool: {tool_name!r}"
        )

    def test_forbids_direct_metric_generation(self) -> None:
        """PLANNER_SYSTEM_PROMPT must include 'NEVER generate' to prohibit free numbers.

        The deterministic boundary rule requires the LLM to never emit
        TSS, CTL, ATL, TSB, ACWR, VO2max, VDOT, or pace values directly.
        """
        assert "NEVER generate" in PLANNER_SYSTEM_PROMPT

    def test_contains_never_directive(self) -> None:
        """PLANNER_SYSTEM_PROMPT must contain at least one NEVER directive.

        NEVER keywords reinforce hard constraints that must not be relaxed.
        """
        assert "NEVER" in PLANNER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# REVIEWER_SYSTEM_PROMPT tests
# ---------------------------------------------------------------------------


class TestReviewerSystemPrompt:
    """Tests for REVIEWER_SYSTEM_PROMPT content and structure."""

    def test_is_non_empty_string(self) -> None:
        """REVIEWER_SYSTEM_PROMPT must be a non-empty string."""
        assert isinstance(REVIEWER_SYSTEM_PROMPT, str)
        assert len(REVIEWER_SYSTEM_PROMPT) > 0

    @pytest.mark.parametrize("section", [
        "CRITICAL CONSTRAINTS",
        "EVALUATION DIMENSIONS",
        "REVIEW WORKFLOW",
        "OUTPUT FORMAT",
    ])
    def test_contains_required_section(self, section: str) -> None:
        """REVIEWER_SYSTEM_PROMPT must contain every structural section header.

        Each section governs a distinct phase of the reviewer's evaluation;
        a missing section means the reviewer will skip that phase.
        """
        assert section in REVIEWER_SYSTEM_PROMPT, (
            f"REVIEWER_SYSTEM_PROMPT is missing section: {section!r}"
        )

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
    def test_mentions_all_tool_names(self, tool_name: str) -> None:
        """REVIEWER_SYSTEM_PROMPT must reference every available tool.

        The reviewer independently spot-checks planner values using the same
        6 tools; any omission could cause missed verification.
        """
        assert tool_name in REVIEWER_SYSTEM_PROMPT, (
            f"REVIEWER_SYSTEM_PROMPT does not mention tool: {tool_name!r}"
        )

    def test_threshold_placeholder_replaced(self) -> None:
        """REVIEWER_SYSTEM_PROMPT must not contain the raw __THRESHOLD__ placeholder.

        The prompt is built with .replace('__THRESHOLD__', str(REVIEW_PASS_THRESHOLD)).
        If that substitution failed, reviewers would see __THRESHOLD__ literally.
        """
        assert "__THRESHOLD__" not in REVIEWER_SYSTEM_PROMPT

    def test_threshold_value_present(self) -> None:
        """REVIEWER_SYSTEM_PROMPT must contain the numeric REVIEW_PASS_THRESHOLD value.

        Confirms the placeholder was replaced with the actual integer constant
        so the reviewer knows the passing score floor.
        """
        assert str(REVIEW_PASS_THRESHOLD) in REVIEWER_SYSTEM_PROMPT

    @pytest.mark.parametrize("dimension", [
        "Safety",
        "Progression",
        "Specificity",
        "Feasibility",
    ])
    def test_contains_four_scoring_dimensions(self, dimension: str) -> None:
        """REVIEWER_SYSTEM_PROMPT must list all 4 scoring dimensions.

        These dimensions map directly to ReviewerScores fields; a missing
        dimension means the reviewer may omit a score and cause a parse error.
        """
        assert dimension in REVIEWER_SYSTEM_PROMPT, (
            f"REVIEWER_SYSTEM_PROMPT missing scoring dimension: {dimension!r}"
        )

    def test_safety_has_double_weight(self) -> None:
        """REVIEWER_SYSTEM_PROMPT must note '2x weight' for the Safety dimension.

        Safety is double-weighted in ReviewerScores.overall; the prompt must
        communicate this so the reviewer calibrates its emphasis accordingly.
        """
        assert "2x weight" in REVIEWER_SYSTEM_PROMPT

    def test_contains_never_directive(self) -> None:
        """REVIEWER_SYSTEM_PROMPT must contain at least one NEVER directive.

        NEVER keywords reinforce the constraint that the reviewer must not
        generate physiological values on its own.
        """
        assert "NEVER" in REVIEWER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Cross-prompt consistency
# ---------------------------------------------------------------------------


class TestPromptConsistency:
    """Tests for consistency between the two system prompts."""

    def test_both_prompts_forbid_free_numbers(self) -> None:
        """Both prompts must contain NEVER to prohibit free physiological numbers.

        The deterministic boundary is the core architectural invariant — both
        agents must be told to use tools, not estimate values.
        """
        assert "NEVER" in PLANNER_SYSTEM_PROMPT
        assert "NEVER" in REVIEWER_SYSTEM_PROMPT

    def test_both_prompts_reference_compute_training_stress(self) -> None:
        """Both prompts must reference compute_training_stress by name.

        This is the most-called tool; if either prompt omits it the agent may
        skip TSS computation and emit free numbers.
        """
        assert "compute_training_stress" in PLANNER_SYSTEM_PROMPT
        assert "compute_training_stress" in REVIEWER_SYSTEM_PROMPT
