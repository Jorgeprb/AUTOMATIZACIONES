"""Add detailed assistant behavior configuration fields.

Revision ID: 20260622_0009
Revises: 20260622_0008
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0009"
down_revision: str | None = "20260622_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist editable behavior, booking, and advanced assistant settings."""
    op.add_column(
        "assistant_configs",
        sa.Column(
            "tone",
            sa.String(length=32),
            server_default="profesional",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "response_length",
            sa.String(length=32),
            server_default="normal",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "ask_patient_name",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "ask_patient_phone",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "ask_general_reason",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "allow_booking_without_worker",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "max_proposed_slots",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "allow_cancellations",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "allow_reschedules",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "natural_confirmation_required",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "avoid_exact_confirmation_phrases",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("additional_instructions", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("forbidden_phrases", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("no_availability_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("missing_calendar_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("emergency_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("human_transfer_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("closing_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "use_prices",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "use_knowledge_base",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "strict_calendar_mode",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_max_proposed_slots",
        "assistant_configs",
        "max_proposed_slots BETWEEN 1 AND 10",
    )


def downgrade() -> None:
    """Remove detailed assistant behavior configuration fields."""
    op.drop_constraint(
        "valid_assistant_max_proposed_slots",
        "assistant_configs",
        type_="check",
    )
    for column_name in (
        "strict_calendar_mode",
        "use_knowledge_base",
        "use_prices",
        "closing_message",
        "human_transfer_message",
        "emergency_message",
        "missing_calendar_message",
        "no_availability_message",
        "forbidden_phrases",
        "additional_instructions",
        "avoid_exact_confirmation_phrases",
        "natural_confirmation_required",
        "allow_reschedules",
        "allow_cancellations",
        "max_proposed_slots",
        "allow_booking_without_worker",
        "ask_general_reason",
        "ask_patient_phone",
        "ask_patient_name",
        "response_length",
        "tone",
    ):
        op.drop_column("assistant_configs", column_name)
