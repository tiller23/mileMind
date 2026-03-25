"""Demo mode constants — fixed IDs for demo user and plans.

These UUIDs are deterministic so the seed script is idempotent
and the frontend can link directly to demo plans.
"""

from __future__ import annotations

import uuid

# Fixed UUID for the demo user (never changes)
DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Fixed UUIDs for the three demo plans
DEMO_PLAN_IDS = {
    "beginner_5k": uuid.UUID("00000000-0000-0000-0000-d00000000001"),
    "intermediate_half": uuid.UUID("00000000-0000-0000-0000-d00000000002"),
    "advanced_marathon": uuid.UUID("00000000-0000-0000-0000-d00000000003"),
}
