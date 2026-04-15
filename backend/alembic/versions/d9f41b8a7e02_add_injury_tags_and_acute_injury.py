"""add injury_tags and acute injury fields

Revision ID: d9f41b8a7e02
Revises: 12168dc934a9
Create Date: 2026-04-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import JSON

from alembic import op

revision: str = "d9f41b8a7e02"
down_revision: str | Sequence[str] | None = "12168dc934a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    jsonb = PG_JSONB().with_variant(JSON, "sqlite")
    # Use a dialect-aware default: explicit JSONB cast on Postgres so the
    # value stored is the JSON array `[]`, not the string "[]".
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        injury_tags_default = sa.text("'[]'::jsonb")
    else:
        injury_tags_default = sa.text("'[]'")
    op.add_column(
        "athlete_profiles",
        sa.Column(
            "injury_tags",
            jsonb,
            nullable=False,
            server_default=injury_tags_default,
        ),
    )
    op.add_column(
        "athlete_profiles",
        sa.Column(
            "current_acute_injury",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "athlete_profiles",
        sa.Column(
            "current_injury_description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("athlete_profiles", "current_injury_description")
    op.drop_column("athlete_profiles", "current_acute_injury")
    op.drop_column("athlete_profiles", "injury_tags")
