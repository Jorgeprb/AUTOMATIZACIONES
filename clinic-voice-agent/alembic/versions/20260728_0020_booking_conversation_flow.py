"""Add configurable service, slot, response and call-closing behavior.

Revision ID: 20260728_0020
Revises: 20260725_0019
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0020"
down_revision: str | None = "20260725_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_configs",
        sa.Column(
            "service_prompt_mode",
            sa.String(length=32),
            server_default=sa.text("'ask_open'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_service_prompt_mode",
        "assistant_configs",
        "service_prompt_mode IN ('list_services', 'ask_open', 'infer_confirm')",
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "slot_interval_minutes",
            sa.Integer(),
            server_default=sa.text("15"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_slot_interval_minutes",
        "assistant_configs",
        "slot_interval_minutes IN (5, 10, 15, 20, 30, 60)",
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "direct_availability_response",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "direct_booking_response",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "booking_confirmation_datetime_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "post_booking_followup_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("post_booking_followup_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "hangup_after_no_more_help",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "hangup_on_natural_goodbye",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    # Preserve the meaning of the legacy boolean for existing configurations.
    op.execute(
        """
        UPDATE assistant_configs
        SET service_prompt_mode = CASE
            WHEN ask_service THEN 'ask_open'
            ELSE 'infer_confirm'
        END
        """
    )


def downgrade() -> None:
    op.drop_column("assistant_configs", "hangup_on_natural_goodbye")
    op.drop_column("assistant_configs", "hangup_after_no_more_help")
    op.drop_column("assistant_configs", "post_booking_followup_message")
    op.drop_column("assistant_configs", "post_booking_followup_enabled")
    op.drop_column("assistant_configs", "booking_confirmation_datetime_enabled")
    op.drop_column("assistant_configs", "direct_booking_response")
    op.drop_column("assistant_configs", "direct_availability_response")
    op.drop_constraint(
        "valid_assistant_slot_interval_minutes",
        "assistant_configs",
        type_="check",
    )
    op.drop_column("assistant_configs", "slot_interval_minutes")
    op.drop_constraint(
        "valid_assistant_service_prompt_mode",
        "assistant_configs",
        type_="check",
    )
    op.drop_column("assistant_configs", "service_prompt_mode")
