"""Enable conversation transcripts for active assistants.

Revision ID: 20260725_0018
Revises: 20260723_0017
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0018"
down_revision: str | None = "20260723_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "assistant_configs",
        "transcript_enabled",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE assistant_configs SET transcript_enabled = true "
        "WHERE is_active = true"
    )


def downgrade() -> None:
    op.alter_column(
        "assistant_configs",
        "transcript_enabled",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
