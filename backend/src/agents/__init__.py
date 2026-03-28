"""Agent layer — Planner/Reviewer orchestration with tool-use loops.

The planner agent uses Claude to generate periodized training plans,
calling deterministic tools for all physiological computations. The
reviewer agent independently evaluates plan safety across 4 dimensions.
The orchestrator drives the planner-reviewer retry loop until convergence.
"""

from src.agents.batch import BatchCoordinator, BatchTransport
from src.agents.orchestrator import OrchestrationResult, Orchestrator
from src.agents.planner import PlannerAgent, PlannerResult
from src.agents.prompts import PLANNER_SYSTEM_PROMPT, REVIEWER_SYSTEM_PROMPT
from src.agents.reviewer import ReviewerAgent, ReviewerResult
from src.agents.shared import AgentLoopResult
from src.agents.transport import AnthropicTransport, MessageTransport
from src.agents.validation import ValidationResult, validate_plan_output

__all__ = [
    "AgentLoopResult",
    "AnthropicTransport",
    "BatchCoordinator",
    "BatchTransport",
    "MessageTransport",
    "OrchestrationResult",
    "Orchestrator",
    "PLANNER_SYSTEM_PROMPT",
    "PlannerAgent",
    "PlannerResult",
    "REVIEWER_SYSTEM_PROMPT",
    "ReviewerAgent",
    "ReviewerResult",
    "ValidationResult",
    "validate_plan_output",
]
