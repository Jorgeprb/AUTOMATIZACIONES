"""Allow workers to inherit the clinic opening hours.

Revision ID: 20260730_0023
Revises: 20260729_0022
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0023"
down_revision: str | None = "20260729_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workers",
        sa.Column(
            "inherit_clinic_hours",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("workers", "inherit_clinic_hours")
