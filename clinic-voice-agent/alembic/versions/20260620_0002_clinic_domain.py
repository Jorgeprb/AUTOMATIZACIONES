"""Add the complete clinic scheduling domain.

This revision replaces the original scaffold-only call and appointment tables.
Those tables were not connected to clinics, workers, or calendars, so their
experimental rows cannot be migrated safely and are intentionally discarded.

Revision ID: 20260620_0002
Revises: 20260620_0001
Create Date: 2026-06-20 00:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260620_0002"
down_revision: str | None = "20260620_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

legacy_call_status = postgresql.ENUM(
    "RECEIVED",
    "ACTIVE",
    "COMPLETED",
    "FAILED",
    name="call_status",
    create_type=False,
)
legacy_appointment_status = postgresql.ENUM(
    "PENDING",
    "CONFIRMED",
    "CANCELLED",
    name="appointment_status",
    create_type=False,
)


def upgrade() -> None:
    """Replace the scaffold schema with the complete clinic domain."""
    op.drop_index("ix_appointments_call_id", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(
        "ix_clinic_calls_openai_call_id",
        table_name="clinic_calls",
    )
    op.drop_table("clinic_calls")
    legacy_appointment_status.drop(op.get_bind(), checkfirst=True)
    legacy_call_status.drop(op.get_bind(), checkfirst=True)

    op.create_table(
        "clinics",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_clinics"),
        sa.UniqueConstraint(
            "phone_number",
            name="uq_clinics_phone_number",
        ),
    )

    op.create_table(
        "workers",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("calendar_id", sa.String(length=320), nullable=False),
        sa.Column("color_id", sa.String(length=32), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "working_hours_json",
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
            ["clinic_id"],
            ["clinics.id"],
            name="fk_workers_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workers"),
        sa.UniqueConstraint(
            "clinic_id",
            "calendar_id",
            name="uq_workers_clinic_calendar",
        ),
    )
    op.create_index(
        "ix_workers_clinic_id",
        "workers",
        ["clinic_id"],
        unique=False,
    )

    op.create_table(
        "services",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "buffer_before_minutes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "buffer_after_minutes",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
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
        sa.CheckConstraint(
            "buffer_after_minutes >= 0",
            name="ck_services_nonnegative_buffer_after",
        ),
        sa.CheckConstraint(
            "buffer_before_minutes >= 0",
            name="ck_services_nonnegative_buffer_before",
        ),
        sa.CheckConstraint(
            "duration_minutes > 0",
            name="ck_services_positive_duration",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_services_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint(
            "clinic_id",
            "name",
            name="uq_services_clinic_name",
        ),
    )
    op.create_index(
        "ix_services_clinic_id",
        "services",
        ["clinic_id"],
        unique=False,
    )

    op.create_table(
        "call_sessions",
        sa.Column("openai_call_id", sa.String(length=128), nullable=False),
        sa.Column("provider_call_id", sa.String(length=128), nullable=True),
        sa.Column("caller_phone", sa.String(length=32), nullable=False),
        sa.Column("called_number", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=11),
            server_default=sa.text("'incoming'"),
            nullable=False,
        ),
        sa.Column(
            "conversation_state_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('incoming', 'active', 'completed', 'failed', 'transferred')",
            name="ck_call_sessions_call_session_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_call_sessions"),
    )
    op.create_index(
        "ix_call_sessions_openai_call_id",
        "call_sessions",
        ["openai_call_id"],
        unique=False,
    )

    op.create_table(
        "appointments",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("google_calendar_id", sa.String(length=320), nullable=False),
        sa.Column("google_event_id", sa.String(length=256), nullable=False),
        sa.Column("patient_name", sa.String(length=200), nullable=False),
        sa.Column("patient_phone", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=9),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=9),
            server_default=sa.text("'voice_bot'"),
            nullable=False,
        ),
        sa.Column("call_session_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "source IN ('voice_bot')",
            name="ck_appointments_appointment_source",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'failed')",
            name="ck_appointments_appointment_status",
        ),
        sa.CheckConstraint(
            "end_at > start_at",
            name="ck_appointments_valid_time_range",
        ),
        sa.ForeignKeyConstraint(
            ["call_session_id"],
            ["call_sessions.id"],
            name="fk_appointments_call_session_id_call_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_appointments_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_appointments_service_id_services",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
            name="fk_appointments_worker_id_workers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
        sa.UniqueConstraint(
            "google_calendar_id",
            "google_event_id",
            name="uq_appointments_google_event",
        ),
    )
    op.create_index(
        "ix_appointments_clinic_id",
        "appointments",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        "ix_appointments_patient_phone",
        "appointments",
        ["patient_phone"],
        unique=False,
    )
    op.create_index(
        "ix_appointments_worker_schedule",
        "appointments",
        ["worker_id", "start_at", "end_at"],
        unique=False,
    )

    op.create_table(
        "call_events",
        sa.Column("call_session_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column(
            "payload_json",
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
        sa.ForeignKeyConstraint(
            ["call_session_id"],
            ["call_sessions.id"],
            name="fk_call_events_call_session_id_call_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_call_events"),
    )
    op.create_index(
        "ix_call_events_call_session_id",
        "call_events",
        ["call_session_id"],
        unique=False,
    )

    op.create_table(
        "google_credentials",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("token_json_encrypted", sa.Text(), nullable=False),
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
            ["clinic_id"],
            ["clinics.id"],
            name="fk_google_credentials_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_google_credentials"),
        sa.UniqueConstraint(
            "clinic_id",
            "account_email",
            name="uq_google_credentials_clinic_account",
        ),
    )
    op.create_index(
        "ix_google_credentials_clinic_id",
        "google_credentials",
        ["clinic_id"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the original scaffold-only call and appointment tables."""
    op.drop_index(
        "ix_google_credentials_clinic_id",
        table_name="google_credentials",
    )
    op.drop_table("google_credentials")
    op.drop_index(
        "ix_call_events_call_session_id",
        table_name="call_events",
    )
    op.drop_table("call_events")
    op.drop_index(
        "ix_appointments_worker_schedule",
        table_name="appointments",
    )
    op.drop_index(
        "ix_appointments_patient_phone",
        table_name="appointments",
    )
    op.drop_index(
        "ix_appointments_clinic_id",
        table_name="appointments",
    )
    op.drop_table("appointments")
    op.drop_index(
        "ix_call_sessions_openai_call_id",
        table_name="call_sessions",
    )
    op.drop_table("call_sessions")
    op.drop_index("ix_services_clinic_id", table_name="services")
    op.drop_table("services")
    op.drop_index("ix_workers_clinic_id", table_name="workers")
    op.drop_table("workers")
    op.drop_table("clinics")

    legacy_call_status.create(op.get_bind(), checkfirst=True)
    legacy_appointment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clinic_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("openai_call_id", sa.String(length=128), nullable=True),
        sa.Column("caller_number", sa.String(length=32), nullable=True),
        sa.Column("status", legacy_call_status, nullable=False),
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
        sa.Column("status", legacy_appointment_status, nullable=False),
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
