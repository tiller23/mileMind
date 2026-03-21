"""Output validation for planner agent responses.

Verifies that the planner's text output meets structural requirements.
TSS values are computed in post-processing, so tool-grounding checks
for compute_training_stress are no longer required.

Structural checks (used by both planner-only and orchestrated modes):
- Plan text is non-empty
- validate_progression_constraints was called at least once
- All tool calls succeeded

In orchestrated mode (Phase 3), this validation serves as a pre-filter:
plans that fail structural validation skip the reviewer and trigger an
immediate planner retry, saving reviewer API costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Result of validating a planner's output against tool call evidence.

    Attributes:
        passed: True if all validation checks passed.
        issues: List of human-readable descriptions of validation failures.
            Empty when passed is True.
    """

    passed: bool
    issues: list[str] = field(default_factory=list)


def validate_plan_output(
    plan_text: str,
    tool_calls: list[dict[str, Any]],
) -> ValidationResult:
    """Validate that the planner's output meets structural requirements.

    Checks:
    1. The plan text is non-empty.
    2. validate_progression_constraints was called at least once (safety
       validation is mandatory before finalizing any plan).
    3. All tool calls that were made succeeded (no unresolved errors).

    Note: compute_training_stress is no longer required because TSS values
    are computed in post-processing by the deterministic engine.

    Args:
        plan_text: The raw text response from the planner agent.
        tool_calls: List of tool call records, each a dict with keys:
            name (str), input (dict), output (dict), success (bool).

    Returns:
        ValidationResult with passed=True if all checks pass, otherwise
        passed=False with a list of specific issues found.
    """
    issues: list[str] = []

    # Check 1: Non-empty plan text
    if not plan_text or not plan_text.strip():
        issues.append("Plan text is empty. The planner did not produce a response.")

    # Check 2: validate_progression_constraints must have been called
    validation_calls = [
        tc for tc in tool_calls if tc["name"] == "validate_progression_constraints"
    ]
    if not validation_calls:
        issues.append(
            "validate_progression_constraints was never called. Safety validation "
            "is mandatory before finalizing any training plan."
        )

    # Check 3: All tool calls should have succeeded
    failed_calls = [tc for tc in tool_calls if not tc.get("success", False)]
    if failed_calls:
        failed_names = [tc["name"] for tc in failed_calls]
        issues.append(
            f"{len(failed_calls)} tool call(s) failed: {', '.join(failed_names)}. "
            "The planner should retry failed tool calls or adjust inputs."
        )

    return ValidationResult(
        passed=len(issues) == 0,
        issues=issues,
    )
