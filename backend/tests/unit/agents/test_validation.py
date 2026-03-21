"""Unit tests for planner output validation.

Tests validate_plan_output as a pure function — no mocking or async needed.
"""

import pytest

from src.agents.validation import ValidationResult, validate_plan_output


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_passed_result(self) -> None:
        r = ValidationResult(passed=True)
        assert r.passed is True
        assert r.issues == []

    def test_failed_result(self) -> None:
        r = ValidationResult(passed=False, issues=["Problem"])
        assert r.passed is False
        assert r.issues == ["Problem"]


class TestValidatePlanOutput:
    """Tests for validate_plan_output function."""

    VALID_TOOL_CALLS = [
        {"name": "validate_progression_constraints", "input": {}, "output": {"valid": True}, "success": True},
    ]

    def test_valid_plan_passes(self) -> None:
        result = validate_plan_output("A valid plan with details.", self.VALID_TOOL_CALLS)
        assert result.passed is True
        assert result.issues == []

    def test_empty_plan_text_fails(self) -> None:
        result = validate_plan_output("", self.VALID_TOOL_CALLS)
        assert result.passed is False
        assert any("empty" in issue.lower() for issue in result.issues)

    def test_whitespace_only_plan_text_fails(self) -> None:
        result = validate_plan_output("   ", self.VALID_TOOL_CALLS)
        assert result.passed is False
        assert any("empty" in issue.lower() for issue in result.issues)

    def test_compute_training_stress_not_required(self) -> None:
        """compute_training_stress is no longer required — TSS is computed post-hoc."""
        tool_calls = [
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is True

    def test_missing_validate_progression_fails(self) -> None:
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is False
        assert any("validate_progression_constraints" in issue for issue in result.issues)

    def test_failed_tool_call_fails(self) -> None:
        tool_calls = [
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": False},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is False
        assert any("failed" in issue.lower() for issue in result.issues)

    def test_missing_success_key_treated_as_failure(self) -> None:
        tool_calls = [
            {"name": "compute_training_stress", "input": {}, "output": {}},
            {"name": "validate_progression_constraints", "input": {}, "output": {}, "success": True},
        ]
        result = validate_plan_output("Plan text.", tool_calls)
        assert result.passed is False

    def test_no_tool_calls_fails(self) -> None:
        result = validate_plan_output("Plan text.", [])
        assert result.passed is False
        assert len(result.issues) == 1  # missing validate_progression_constraints

    def test_multiple_issues_accumulated(self) -> None:
        result = validate_plan_output("", [])
        assert result.passed is False
        assert len(result.issues) == 2  # empty text + missing validate_progression
