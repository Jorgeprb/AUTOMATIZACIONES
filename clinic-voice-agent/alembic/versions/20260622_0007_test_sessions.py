"""Add persistent browser assistant test sessions.

Revision ID: 20260622_0007
Revises: 20260622_0006
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0007"
down_revision: str | None = "20260622_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the test-session persistence table."""
    op.create_table(
        "test_sessions",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_config_id", sa.Uuid(), nullable=False),
        sa.Column(
            "use_real_calendar",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "messages_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "state_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assistant_config_id"],
            ["assistant_configs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_test_sessions_clinic_id"),
        "test_sessions",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_sessions_assistant_config_id"),
        "test_sessions",
        ["assistant_config_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop test-session persistence."""
    op.drop_index(
        op.f("ix_test_sessions_assistant_config_id"),
        table_name="test_sessions",
    )
    op.drop_index(
        op.f("ix_test_sessions_clinic_id"),
        table_name="test_sessions",
    )
    op.drop_table("test_sessions")
