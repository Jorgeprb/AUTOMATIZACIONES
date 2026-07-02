"""Add imported knowledge metadata.

Revision ID: 20260622_0010
Revises: 20260622_0009
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0010"
down_revision: str | None = "20260622_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store source and import status for PDF/URL knowledge items."""
    op.add_column(
        "knowledge_items",
        sa.Column(
            "source_type",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_items",
        sa.Column("source", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "knowledge_items",
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_items",
        sa.Column(
            "import_status",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove imported knowledge metadata."""
    op.drop_column("knowledge_items", "import_status")
    op.drop_column("knowledge_items", "imported_at")
    op.drop_column("knowledge_items", "source")
    op.drop_column("knowledge_items", "source_type")
