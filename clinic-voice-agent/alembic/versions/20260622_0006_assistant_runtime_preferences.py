"""Add per-assistant call privacy and retention preferences.

Revision ID: 20260622_0006
Revises: 20260621_0005
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0006"
down_revision: str | None = "20260621_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add runtime preferences to assistant configurations."""
    op.add_column(
        "assistant_configs",
        sa.Column(
            "transcript_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "recording_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "conversation_retention_days",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_assistant_configs_valid_retention_days",
        "assistant_configs",
        "conversation_retention_days BETWEEN 1 AND 3650",
    )


def downgrade() -> None:
    """Remove runtime preferences from assistant configurations."""
    op.drop_constraint(
        "ck_assistant_configs_valid_retention_days",
        "assistant_configs",
        type_="check",
    )
    op.drop_column("assistant_configs", "conversation_retention_days")
    op.drop_column("assistant_configs", "recording_enabled")
    op.drop_column("assistant_configs", "transcript_enabled")
