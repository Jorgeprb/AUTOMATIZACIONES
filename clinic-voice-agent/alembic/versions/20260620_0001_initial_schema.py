"""Create initial call and appointment tables.

Revision ID: 20260620_0001
Revises:
Create Date: 2026-06-20 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260620_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

call_status = postgresql.ENUM(
    "RECEIVED",
    "ACTIVE",
    "COMPLETED",
    "FAILED",
    name="call_status",
    create_type=False,
)
appointment_status = postgresql.ENUM(
    "PENDING",
    "CONFIRMED",
    "CANCELLED",
    name="appointment_status",
    create_type=False,
)


def upgrade() -> None:
    """Create the initial persistence schema."""
    call_status.create(op.get_bind(), checkfirst=True)
    appointment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clinic_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("openai_call_id", sa.String(length=128), nullable=True),
        sa.Column("caller_number", sa.String(length=32), nullable=True),
        sa.Column("status", call_status, nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_clinic_calls"),
        sa.UniqueConstraint(
            "openai_call_id",
            name="uq_clinic_calls_openai_call_id",
        ),
    )
    op.create_index(
        "ix_clinic_calls_openai_call_id",
        "clinic_calls",
        ["openai_call_id"],
        unique=False,
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("google_event_id", sa.String(length=256), nullable=True),
        sa.Column("patient_name", sa.String(length=200), nullable=False),
        sa.Column("patient_phone", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", appointment_status, nullable=False),
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
            ["call_id"],
            ["clinic_calls.id"],
            name="fk_appointments_call_id_clinic_calls",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
        sa.UniqueConstraint(
            "google_event_id",
            name="uq_appointments_google_event_id",
        ),
    )
    op.create_index(
        "ix_appointments_call_id",
        "appointments",
        ["call_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the initial persistence schema."""
    op.drop_index("ix_appointments_call_id", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(
        "ix_clinic_calls_openai_call_id",
        table_name="clinic_calls",
    )
    op.drop_table("clinic_calls")
    appointment_status.drop(op.get_bind(), checkfirst=True)
    call_status.drop(op.get_bind(), checkfirst=True)
