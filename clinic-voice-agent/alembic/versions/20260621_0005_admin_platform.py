"""Add the multi-clinic administration platform domain.

Revision ID: 20260621_0005
Revises: 20260621_0004
Create Date: 2026-06-21 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260621_0005"
down_revision: str | None = "20260621_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    """Create administrative configuration and content resources."""
    op.drop_constraint("uq_clinics_phone_number", "clinics", type_="unique")
    op.alter_column(
        "clinics",
        "phone_number",
        new_column_name="main_phone_number",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "uq_clinics_main_phone_number",
        "clinics",
        ["main_phone_number"],
    )
    op.add_column("clinics", sa.Column("legal_name", sa.String(240), nullable=True))
    op.add_column(
        "clinics",
        sa.Column(
            "default_language",
            sa.String(16),
            server_default=sa.text("'es'"),
            nullable=False,
        ),
    )
    op.add_column("clinics", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("clinics", sa.Column("website", sa.String(500), nullable=True))
    op.add_column("clinics", sa.Column("email", sa.String(320), nullable=True))
    op.add_column("clinics", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "clinics",
        sa.Column(
            "opening_hours_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "clinics",
        sa.Column("emergency_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "clinics",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    op.add_column(
        "workers",
        sa.Column("public_description", sa.Text(), nullable=True),
    )
    op.add_column(
        "workers",
        sa.Column("phone_extension", sa.String(32), nullable=True),
    )
    op.add_column("workers", sa.Column("email", sa.String(320), nullable=True))

    op.add_column(
        "services",
        sa.Column("public_name", sa.String(200), nullable=True),
    )
    op.execute("UPDATE services SET public_name = name")
    op.alter_column(
        "services",
        "public_name",
        existing_type=sa.String(200),
        nullable=False,
    )
    op.add_column("services", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "services",
        sa.Column("price_text", sa.String(200), nullable=True),
    )
    op.add_column(
        "services",
        sa.Column("price_amount", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "services",
        sa.Column(
            "currency",
            sa.String(3),
            server_default=sa.text("'EUR'"),
            nullable=False,
        ),
    )
    op.add_column(
        "services",
        sa.Column(
            "requires_worker",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "services",
        sa.Column("allowed_worker_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "services",
        sa.Column(
            "is_bookable_by_bot",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    op.create_table(
        "phone_numbers",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=10),
            server_default=sa.text("'other'"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("sip_target", sa.String(500), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "provider IN ('voipstudio', 'twilio', 'other')",
            name="ck_phone_numbers_phone_provider",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_phone_numbers_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_phone_numbers"),
        sa.UniqueConstraint(
            "phone_number",
            name="uq_phone_numbers_phone_number",
        ),
    )
    op.create_index(
        "ix_phone_numbers_clinic_id",
        "phone_numbers",
        ["clinic_id"],
        unique=False,
    )

    op.create_table(
        "assistant_configs",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("realtime_model", sa.String(120), nullable=False),
        sa.Column("realtime_voice", sa.String(80), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=True),
        sa.Column("first_message", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("safety_prompt", sa.Text(), nullable=False),
        sa.Column("booking_policy_prompt", sa.Text(), nullable=False),
        sa.Column("cancellation_policy_prompt", sa.Text(), nullable=False),
        sa.Column("transfer_policy_prompt", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_assistant_configs_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_configs"),
    )
    op.create_index(
        "ix_assistant_configs_clinic_id",
        "assistant_configs",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        "uq_assistant_configs_one_active_per_clinic",
        "assistant_configs",
        ["clinic_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "knowledge_items",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("category", sa.String(9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "category IN ('prices', 'services', 'faq', 'policy', "
            "'location', 'insurance', 'custom')",
            name="ck_knowledge_items_knowledge_category",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_knowledge_items_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_items"),
    )
    op.create_index(
        "ix_knowledge_items_clinic_id",
        "knowledge_items",
        ["clinic_id"],
        unique=False,
    )

    op.create_table(
        "conversation_flows",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "flow_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name="fk_conversation_flows_clinic_id_clinics",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_flows"),
    )
    op.create_index(
        "ix_conversation_flows_clinic_id",
        "conversation_flows",
        ["clinic_id"],
        unique=False,
    )

    op.add_column(
        "call_sessions",
        sa.Column("phone_number_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("assistant_config_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("caller_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("detected_intent", sa.String(160), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("outcome", sa.String(19), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column(
            "recording_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "call_sessions",
        sa.Column(
            "transcript_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_call_sessions_call_outcome",
        "call_sessions",
        "outcome IS NULL OR outcome IN "
        "('appointment_created', 'cancelled', 'transferred', 'no_action', 'failed')",
    )
    op.create_foreign_key(
        "fk_call_sessions_phone_number_id_phone_numbers",
        "call_sessions",
        "phone_numbers",
        ["phone_number_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_call_sessions_assistant_config_id_assistant_configs",
        "call_sessions",
        "assistant_configs",
        ["assistant_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_call_sessions_phone_number_id",
        "call_sessions",
        ["phone_number_id"],
        unique=False,
    )
    op.create_index(
        "ix_call_sessions_assistant_config_id",
        "call_sessions",
        ["assistant_config_id"],
        unique=False,
    )

    op.drop_constraint(
        "ck_appointments_appointment_source",
        "appointments",
        type_="check",
    )
    op.alter_column(
        "appointments",
        "source",
        existing_type=sa.String(9),
        type_=sa.String(11),
        existing_nullable=False,
        existing_server_default=sa.text("'voice_bot'"),
    )
    op.create_check_constraint(
        "ck_appointments_appointment_source",
        "appointments",
        "source IN ('voice_bot', 'admin_panel')",
    )


def downgrade() -> None:
    """Remove the administration platform resources."""
    op.drop_constraint(
        "ck_appointments_appointment_source",
        "appointments",
        type_="check",
    )
    op.alter_column(
        "appointments",
        "source",
        existing_type=sa.String(11),
        type_=sa.String(9),
        existing_nullable=False,
        existing_server_default=sa.text("'voice_bot'"),
    )
    op.create_check_constraint(
        "ck_appointments_appointment_source",
        "appointments",
        "source IN ('voice_bot')",
    )

    op.drop_index(
        "ix_call_sessions_assistant_config_id",
        table_name="call_sessions",
    )
    op.drop_index(
        "ix_call_sessions_phone_number_id",
        table_name="call_sessions",
    )
    op.drop_constraint(
        "fk_call_sessions_assistant_config_id_assistant_configs",
        "call_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_call_sessions_phone_number_id_phone_numbers",
        "call_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_call_sessions_call_outcome",
        "call_sessions",
        type_="check",
    )
    op.drop_column("call_sessions", "transcript_enabled")
    op.drop_column("call_sessions", "recording_enabled")
    op.drop_column("call_sessions", "outcome")
    op.drop_column("call_sessions", "detected_intent")
    op.drop_column("call_sessions", "caller_name")
    op.drop_column("call_sessions", "assistant_config_id")
    op.drop_column("call_sessions", "phone_number_id")

    op.drop_index(
        "ix_conversation_flows_clinic_id",
        table_name="conversation_flows",
    )
    op.drop_table("conversation_flows")
    op.drop_index("ix_knowledge_items_clinic_id", table_name="knowledge_items")
    op.drop_table("knowledge_items")
    op.drop_index(
        "uq_assistant_configs_one_active_per_clinic",
        table_name="assistant_configs",
    )
    op.drop_index(
        "ix_assistant_configs_clinic_id",
        table_name="assistant_configs",
    )
    op.drop_table("assistant_configs")
    op.drop_index("ix_phone_numbers_clinic_id", table_name="phone_numbers")
    op.drop_table("phone_numbers")

    op.drop_column("services", "is_bookable_by_bot")
    op.drop_column("services", "allowed_worker_ids")
    op.drop_column("services", "requires_worker")
    op.drop_column("services", "currency")
    op.drop_column("services", "price_amount")
    op.drop_column("services", "price_text")
    op.drop_column("services", "description")
    op.drop_column("services", "public_name")
    op.drop_column("workers", "email")
    op.drop_column("workers", "phone_extension")
    op.drop_column("workers", "public_description")

    op.drop_column("clinics", "is_active")
    op.drop_column("clinics", "emergency_message")
    op.drop_column("clinics", "opening_hours_json")
    op.drop_column("clinics", "description")
    op.drop_column("clinics", "email")
    op.drop_column("clinics", "website")
    op.drop_column("clinics", "address")
    op.drop_column("clinics", "default_language")
    op.drop_column("clinics", "legal_name")
    op.drop_constraint(
        "uq_clinics_main_phone_number",
        "clinics",
        type_="unique",
    )
    op.alter_column(
        "clinics",
        "main_phone_number",
        new_column_name="phone_number",
        existing_type=sa.String(32),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "uq_clinics_phone_number",
        "clinics",
        ["phone_number"],
    )
