"""Progress event models for SSE streaming during plan generation.

These models live in the models layer (not API layer) so they can be
used by the orchestrator without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProgressEventType(str, Enum):
    """Types of progress events emitted during plan generation.

    Attributes:
        JOB_STARTED: Job has begun.
        PLANNER_STARTED: Planner agent starting iteration.
        PLANNER_COMPLETE: Planner agent finished iteration.
        VALIDATION_RESULT: Phase 2 validation outcome.
        REVIEWER_STARTED: Reviewer agent starting.
        REVIEWER_COMPLETE: Reviewer agent finished with scores.
        RETRY: Plan rejected, starting retry.
        TOKEN_BUDGET: Token budget status update.
        JOB_COMPLETE: Job finished successfully.
        JOB_FAILED: Job failed with error.
    """

    JOB_STARTED = "job_started"
    PLANNER_STARTED = "planner_started"
    PLANNER_COMPLETE = "planner_complete"
    VALIDATION_RESULT = "validation_result"
    REVIEWER_STARTED = "reviewer_started"
    REVIEWER_COMPLETE = "reviewer_complete"
    RETRY = "retry"
    TOKEN_BUDGET = "token_budget"
    JOB_COMPLETE = "job_complete"
    JOB_FAILED = "job_failed"


@dataclass
class ProgressEvent:
    """A single progress event for SSE streaming.

    Attributes:
        event_type: Type of event.
        message: Human-readable message.
        data: Additional event data.
        timestamp: When the event occurred.
        sequence: Monotonic sequence number.
    """

    event_type: ProgressEventType
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONB storage and SSE.

        Returns:
            Dict with all event fields.
        """
        return {
            "event_type": self.event_type.value,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
        }
