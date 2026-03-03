"""Agent layer -- Planner/Reviewer orchestration with tool-use loops.

The planner agent uses Claude to generate periodized training plans,
calling deterministic tools for all physiological computations. The
reviewer agent (Phase 3) independently evaluates plan safety.
"""

from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.prompts import PLANNER_SYSTEM_PROMPT
from src.agents.validation import ValidationResult, validate_plan_output

__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "PlannerAgent",
    "PlannerResult",
    "ValidationResult",
    "validate_plan_output",
]
