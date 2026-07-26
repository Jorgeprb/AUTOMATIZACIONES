"""Add turn-end tuning and ensure transcript capture is enabled.

Revision ID: 20260725_0019
Revises: 20260725_0018
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0019"
down_revision: str | None = "20260725_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_configs",
        sa.Column(
            "turn_end_silence_ms",
            sa.Integer(),
            server_default=sa.text("350"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_turn_end_silence_ms",
        "assistant_configs",
        "turn_end_silence_ms BETWEEN 200 AND 1200",
    )
    # The product explicitly exposes conversation transcripts; enable existing
    # configurations once. Administrators can still disable the setting later.
    op.execute("UPDATE assistant_configs SET transcript_enabled = true")


def downgrade() -> None:
    op.drop_constraint(
        "valid_assistant_turn_end_silence_ms",
        "assistant_configs",
        type_="check",
    )
    op.drop_column("assistant_configs", "turn_end_silence_ms")
