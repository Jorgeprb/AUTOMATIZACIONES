"""Enforce one Google OAuth account per clinic.

Revision ID: 20260620_0003
Revises: 20260620_0002
Create Date: 2026-06-20 01:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260620_0003"
down_revision: str | None = "20260620_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Limit each clinic to one stored Google credential."""
    op.alter_column(
        "workers",
        "calendar_id",
        existing_type=sa.String(length=320),
        nullable=True,
    )
    op.execute(
        """
        UPDATE workers
        SET calendar_id = NULL
        WHERE calendar_id LIKE '%@local.invalid'
        """
    )
    op.create_unique_constraint(
        "uq_google_credentials_clinic_id",
        "google_credentials",
        ["clinic_id"],
    )


def downgrade() -> None:
    """Allow multiple Google credentials per clinic again."""
    op.drop_constraint(
        "uq_google_credentials_clinic_id",
        "google_credentials",
        type_="unique",
    )
    op.execute(
        """
        UPDATE workers
        SET calendar_id = 'unlinked-' || id::text || '@local.invalid'
        WHERE calendar_id IS NULL
        """
    )
    op.alter_column(
        "workers",
        "calendar_id",
        existing_type=sa.String(length=320),
        nullable=False,
    )
