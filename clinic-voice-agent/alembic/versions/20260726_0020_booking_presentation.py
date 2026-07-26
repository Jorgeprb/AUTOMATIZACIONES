"""Add spoken-time, caller phone, and calendar event customization.

Revision ID: 20260726_0020
Revises: 20260725_0019
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0020"
down_revision: str | None = "20260725_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_DESCRIPTION = """Reserva creada por asistente telefónico.
Paciente: {patient_name}
Teléfono: {patient_phone}
Servicio: {service_name}
Profesional: {worker_name}
Fecha: {start_date}
Hora: {start_time}
Motivo general: {reason}"""


def upgrade() -> None:
    op.add_column(
        "assistant_configs",
        sa.Column(
            "time_reading_style",
            sa.String(length=24),
            server_default=sa.text("'natural_quarters'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_time_reading_style",
        "assistant_configs",
        "time_reading_style IN ('natural_quarters', 'numeric')",
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "caller_phone_policy",
            sa.String(length=24),
            server_default=sa.text("'ask_before_use'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_caller_phone_policy",
        "assistant_configs",
        "caller_phone_policy IN ('ask_before_use', 'use_directly')",
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "calendar_event_title_template",
            sa.Text(),
            server_default=sa.text("'Cita - {patient_name}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "calendar_event_description_template",
            sa.Text(),
            server_default=sa.text("'" + _DEFAULT_DESCRIPTION.replace("'", "''") + "'"),
            nullable=False,
        ),
    )
    # Align the database with the public UI/provider range already in use.
    # Older deployments allowed 0.25–4.00, so normalize any legacy outliers
    # before installing the tighter constraint.
    op.execute(
        sa.text(
            "UPDATE assistant_configs "
            "SET voice_speed = LEAST(GREATEST(voice_speed, 0.50), 2.00)"
        )
    )
    op.drop_constraint(
        "valid_assistant_voice_speed",
        "assistant_configs",
        type_="check",
    )
    op.create_check_constraint(
        "valid_assistant_voice_speed",
        "assistant_configs",
        "voice_speed BETWEEN 0.50 AND 2.00",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_assistant_voice_speed",
        "assistant_configs",
        type_="check",
    )
    op.create_check_constraint(
        "valid_assistant_voice_speed",
        "assistant_configs",
        "voice_speed BETWEEN 0.25 AND 4.00",
    )
    op.drop_column("assistant_configs", "calendar_event_description_template")
    op.drop_column("assistant_configs", "calendar_event_title_template")
    op.drop_constraint(
        "valid_assistant_caller_phone_policy",
        "assistant_configs",
        type_="check",
    )
    op.drop_column("assistant_configs", "caller_phone_policy")
    op.drop_constraint(
        "valid_assistant_time_reading_style",
        "assistant_configs",
        type_="check",
    )
    op.drop_column("assistant_configs", "time_reading_style")
