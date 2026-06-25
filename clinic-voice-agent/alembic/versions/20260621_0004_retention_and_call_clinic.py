"""Add clinic retention policy and explicit call ownership.

Revision ID: 20260621_0004
Revises: 20260620_0003
Create Date: 2026-06-21 05:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260621_0004"
down_revision: str | None = "20260620_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add retention controls and privacy-oriented constraints."""
    op.add_column(
        "clinics",
        sa.Column(
            "data_retention_days",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_clinics_valid_data_retention_days",
        "clinics",
        "data_retention_days BETWEEN 1 AND 3650",
    )

    op.add_column(
        "call_sessions",
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_call_sessions_clinic_id_clinics",
        "call_sessions",
        "clinics",
        ["clinic_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_call_sessions_clinic_id",
        "call_sessions",
        ["clinic_id"],
        unique=False,
    )

    op.execute(
        """
        UPDATE appointments
        SET reason = left(regexp_replace(reason, '\\s+', ' ', 'g'), 300)
        WHERE reason IS NOT NULL AND char_length(reason) > 300
        """
    )
    op.create_check_constraint(
        "ck_appointments_general_reason_length",
        "appointments",
        "reason IS NULL OR char_length(reason) <= 300",
    )


def downgrade() -> None:
    """Remove retention controls and call ownership."""
    op.drop_constraint(
        "ck_appointments_general_reason_length",
        "appointments",
        type_="check",
    )
    op.drop_index(
        "ix_call_sessions_clinic_id",
        table_name="call_sessions",
    )
    op.drop_constraint(
        "fk_call_sessions_clinic_id_clinics",
        "call_sessions",
        type_="foreignkey",
    )
    op.drop_column("call_sessions", "clinic_id")
    op.drop_constraint(
        "ck_clinics_valid_data_retention_days",
        "clinics",
        type_="check",
    )
    op.drop_column("clinics", "data_retention_days")
