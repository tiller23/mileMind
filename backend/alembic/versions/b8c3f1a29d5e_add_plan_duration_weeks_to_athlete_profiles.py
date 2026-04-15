"""add plan_duration_weeks to athlete_profiles

Revision ID: b8c3f1a29d5e
Revises: a4d58c24e1dc
Create Date: 2026-03-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c3f1a29d5e"
down_revision: str | Sequence[str] | None = "a4d58c24e1dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "athlete_profiles",
        sa.Column("plan_duration_weeks", sa.Integer(), nullable=False, server_default="12"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("athlete_profiles", "plan_duration_weeks")
