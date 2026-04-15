"""Security hardening: token encryption, JWT revocation, invite codes, user roles.

Revision ID: c3e8a71f5d20
Revises: a4d58c24e1dc
Create Date: 2026-03-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "c3e8a71f5d20"
down_revision: str | None = "b8c3f1a29d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply security hardening schema changes."""
    # Widen Strava token columns for Fernet ciphertext
    op.alter_column(
        "strava_tokens",
        "access_token",
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "strava_tokens",
        "refresh_token",
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=False,
    )

    # Add user role and invite code fields
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="user"))
    op.add_column("users", sa.Column("invite_code_used", sa.String(20), nullable=True))

    # Revoked tokens table for JWT logout
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(36), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Invite codes table
    op.create_table(
        "invite_codes",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    """Revert security hardening schema changes."""
    op.drop_table("invite_codes")
    op.drop_table("revoked_tokens")
    op.drop_column("users", "invite_code_used")
    op.drop_column("users", "role")
    op.alter_column(
        "strava_tokens",
        "refresh_token",
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=False,
    )
    op.alter_column(
        "strava_tokens",
        "access_token",
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=False,
    )
