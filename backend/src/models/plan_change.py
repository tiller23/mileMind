"""Plan change type for conditional review routing."""

from enum import Enum


class PlanChangeType(str, Enum):
    """Categorizes the scope of a plan change request.

    Determines how much reviewer oversight the orchestrator applies:
    - FULL: New plan from scratch. Full reviewer pass with all retries.
    - ADAPTATION: Mid-cycle adjustment. Lightweight review (1 retry).
    - TWEAK: Single workout swap or minor edit. Planner only, no reviewer.
    """

    FULL = "full"
    ADAPTATION = "adaptation"
    TWEAK = "tweak"
