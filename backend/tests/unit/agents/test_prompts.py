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

    def test_safety_rules_before_workflow(self) -> None:
        """Safety rules appear before the planning workflow.

        WHY: In the eval run, the planner ignored safety rules that were at the
        bottom of the prompt. Moving them before the workflow ensures they are
        read first and applied throughout plan generation.
        """
        safety_pos = PLANNER_SYSTEM_PROMPT.index("SAFETY RULES")
        workflow_pos = PLANNER_SYSTEM_PROMPT.index("PLANNING WORKFLOW")
        assert safety_pos < workflow_pos, (
            "SAFETY RULES must appear before PLANNING WORKFLOW in the prompt"
        )

    def test_contains_pace_zone_table(self) -> None:
        """PLANNER_SYSTEM_PROMPT must define numbered pace zones (Zone 1-6).

        WHY: The eval output used vague labels like 'easy' and 'repetition'.
        Numbered zones map to Daniels paces and give athletes clearer guidance.
        """
        for zone_num in range(1, 7):
            assert f"Zone {zone_num}" in PLANNER_SYSTEM_PROMPT, (
                f"PLANNER_SYSTEM_PROMPT missing Zone {zone_num} definition"
            )

    def test_contains_athlete_level_guidelines(self) -> None:
        """PLANNER_SYSTEM_PROMPT must include level-specific coaching guidelines.

        WHY: Without level awareness, the planner prescribed VO2max intervals
        for a beginner. The prompt must differentiate beginner/intermediate/advanced.
        """
        assert "Beginners" in PLANNER_SYSTEM_PROMPT
        assert "Intermediate" in PLANNER_SYSTEM_PROMPT
        assert "Advanced" in PLANNER_SYSTEM_PROMPT

    def test_contains_recovery_week_mandate(self) -> None:
        """Recovery weeks are explicitly called out as mandatory.

        WHY: The eval run's beginner plan had zero recovery weeks, which was
        the primary reason for rejection. The prompt must be unambiguous.
        """
        assert "recovery week" in PLANNER_SYSTEM_PROMPT.lower()
        # Check for strong language about recovery weeks
        assert "mandatory" in PLANNER_SYSTEM_PROMPT.lower() or "WILL be rejected" in PLANNER_SYSTEM_PROMPT

    def test_contains_per_phase_validation(self) -> None:
        """PLANNER_SYSTEM_PROMPT instructs validation after each phase.

        WHY: The eval plan validated only at the end, by which point errors
        had compounded. Per-phase validation catches violations early.
        """
        assert "at least twice" in PLANNER_SYSTEM_PROMPT

    def test_contains_injury_nuance_guidelines(self) -> None:
        """PLANNER_SYSTEM_PROMPT includes nuanced injury handling.

        WHY: The old prompt had a blanket 'avoid workout types that aggravate',
        but past healed injuries should only trigger supplementary exercises,
        not blanket restrictions.
        """
        assert "Past injuries" in PLANNER_SYSTEM_PROMPT or "past injuries" in PLANNER_SYSTEM_PROMPT
        assert "strengthening" in PLANNER_SYSTEM_PROMPT.lower()

    def test_long_runs_not_always_easy(self) -> None:
        """PLANNER_SYSTEM_PROMPT acknowledges long runs can include Zone 3.

        WHY: The eval output had all long runs at easy pace. Zone 3 long runs
        (e.g., progression runs) are normal for intermediate+ athletes.
        """
        assert "NOT always Zone 2" in PLANNER_SYSTEM_PROMPT or "Zone 3" in PLANNER_SYSTEM_PROMPT

    def test_seiler_80_20_citation(self) -> None:
        """PLANNER_SYSTEM_PROMPT cites Seiler for the 80/20 rule.

        WHY: The user asked where the 80/20 rule comes from. Citing the source
        provides credibility and helps users understand the basis.
        """
        assert "Seiler" in PLANNER_SYSTEM_PROMPT

    def test_workout_variety_guidance(self) -> None:
        """PLANNER_SYSTEM_PROMPT instructs rotating quality session types.

        WHY: The eval plan repeated hill repeats every build week. Rotating
        workout types develops different systems and prevents staleness.
        """
        assert "WORKOUT VARIETY" in PLANNER_SYSTEM_PROMPT
        assert "rotate" in PLANNER_SYSTEM_PROMPT.lower()

    def test_prescription_format_guidance(self) -> None:
        """PLANNER_SYSTEM_PROMPT specifies distance vs duration prescription.

        WHY: The eval plan gave duration for everything. Quality sessions need
        distance + structure; easy runs benefit from duration-based prescription.
        """
        assert "WORKOUT PRESCRIPTION FORMAT" in PLANNER_SYSTEM_PROMPT
        assert "DURATION" in PLANNER_SYSTEM_PROMPT
        assert "DISTANCE" in PLANNER_SYSTEM_PROMPT

    def test_recovery_week_calibration(self) -> None:
        """Recovery weeks should be 20-30% reduction, not 50%.

        WHY: The eval plan had 50% drops for recovery weeks, which is too
        aggressive and disrupts training continuity.
        """
        assert "NOT 50%" in PLANNER_SYSTEM_PROMPT
        assert "every 4 building weeks" in PLANNER_SYSTEM_PROMPT

    def test_experienced_base_phase(self) -> None:
        """Advanced athletes should start at their current weekly mileage.

        WHY: The eval plan ramped up from below the athlete's 100 km/week base.
        Experienced runners don't need to build up from a lower starting point.
        """
        assert "start at" in PLANNER_SYSTEM_PROMPT.lower()
        assert "current weekly mileage" in PLANNER_SYSTEM_PROMPT.lower()

    def test_fartlek_definition_required(self) -> None:
        """Vague terms like 'fartlek' must include specific structure.

        WHY: The user asked 'what is this?' about fartlek in the eval output.
        Workouts should be self-explanatory without coaching jargon.
        """
        assert "fartlek" in PLANNER_SYSTEM_PROMPT.lower()
        assert "specific" in PLANNER_SYSTEM_PROMPT.lower()

    def test_peak_phase_not_highest_volume(self) -> None:
        """Peak phase should sharpen with intensity, not maximize volume.

        WHY: The eval plan had peak weeks (510-537 TSS) as the highest-volume
        weeks. Peak is about sharpness, not maximum load.
        """
        assert "sharpening" in PLANNER_SYSTEM_PROMPT.lower() or "sharpen" in PLANNER_SYSTEM_PROMPT.lower()
        assert "NOT make peak" in PLANNER_SYSTEM_PROMPT or "not maximum volume" in PLANNER_SYSTEM_PROMPT.lower()

    def test_weekly_coaching_notes_mandate(self) -> None:
        """Every week must include purpose-explaining notes.

        WHY: The user praised weekly coaching notes as building trust and
        engagement. This is a key differentiator.
        """
        assert "WEEKLY COACHING NOTES" in PLANNER_SYSTEM_PROMPT
        assert "PURPOSE" in PLANNER_SYSTEM_PROMPT

    def test_build_phase_splitting_guidance(self) -> None:
        """Planner is guided to split build into sub-phases for longer plans.

        WHY: The eval plan's Build 2 phase split was praised as a 'nice touch'.
        Encourage this for 12+ week plans.
        """
        assert "BUILD 1" in PLANNER_SYSTEM_PROMPT or "Build 1" in PLANNER_SYSTEM_PROMPT
        assert "BUILD 2" in PLANNER_SYSTEM_PROMPT or "Build 2" in PLANNER_SYSTEM_PROMPT


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

    def test_specificity_is_level_aware(self) -> None:
        """Reviewer specificity criteria differentiates athlete levels.

        WHY: The old prompt said '5K plans should include VO2max sessions',
        which penalized beginner plans for not having VO2max work — then the
        planner added VO2max and got penalized for safety. No-win scenario.
        """
        assert "Beginners" in REVIEWER_SYSTEM_PROMPT or "beginner" in REVIEWER_SYSTEM_PROMPT.lower()
        # Should NOT have the old blanket statement
        assert "5K plan should include intervals and VO2max" not in REVIEWER_SYSTEM_PROMPT

    def test_long_run_assessment_section(self) -> None:
        """Reviewer includes nuanced long run intensity guidance.

        WHY: Long runs at Zone 3 are normal for intermediate+ athletes.
        The reviewer should not penalize progression long runs.
        """
        assert "LONG RUN ASSESSMENT" in REVIEWER_SYSTEM_PROMPT or "Long Run" in REVIEWER_SYSTEM_PROMPT

    def test_injury_history_assessment_section(self) -> None:
        """Reviewer includes nuanced injury assessment guidance.

        WHY: Past healed injuries should not trigger automatic rejection.
        """
        assert "INJURY HISTORY" in REVIEWER_SYSTEM_PROMPT or "Past injuries" in REVIEWER_SYSTEM_PROMPT

    def test_seiler_citation_in_reviewer(self) -> None:
        """Reviewer also cites Seiler for the 80/20 intensity distribution."""
        assert "Seiler" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_workout_variety(self) -> None:
        """Reviewer checks that quality sessions rotate across weeks."""
        assert "rotate across weeks" in REVIEWER_SYSTEM_PROMPT.lower()

    def test_reviewer_peak_phase_assessment(self) -> None:
        """Reviewer scores down if peak weeks are the highest volume."""
        assert "highest-volume weeks" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_recovery_week_calibration(self) -> None:
        """Reviewer expects 20-30% recovery drops, not 50%."""
        assert "NOT 50%" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prescription_format(self) -> None:
        """Reviewer checks workout prescription format (distance vs duration)."""
        assert "Quality sessions should specify distance" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_coaching_notes(self) -> None:
        """Reviewer evaluates presence of weekly coaching notes."""
        assert "coaching notes" in REVIEWER_SYSTEM_PROMPT.lower() or "weekly notes" in REVIEWER_SYSTEM_PROMPT.lower()


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
