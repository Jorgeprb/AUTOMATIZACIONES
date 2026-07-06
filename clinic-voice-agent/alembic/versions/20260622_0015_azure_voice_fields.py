"""Add Azure voice metadata to assistant configs.

Revision ID: 20260622_0015
Revises: 20260622_0014
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0015"
down_revision: str | None = "20260622_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add provider-specific voice fields used by Azure and bridge mode."""
    op.add_column(
        "assistant_configs",
        sa.Column("azure_speech_region", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_style", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    """Remove provider-specific voice fields."""
    op.drop_column("assistant_configs", "voice_style")
    op.drop_column("assistant_configs", "azure_speech_region")
