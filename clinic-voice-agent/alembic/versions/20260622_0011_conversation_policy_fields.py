"""Add assistant conversation policy fields.

Revision ID: 20260622_0011
Revises: 20260622_0010
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0011"
down_revision: str | None = "20260622_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist flexible conversation policy switches for each assistant."""
    op.add_column(
        "assistant_configs",
        sa.Column(
            "allow_bookings",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "allow_price_answers",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "ask_service",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "max_consecutive_questions",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "conversation_style",
            sa.String(length=32),
            server_default="natural",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "initiative_level",
            sa.String(length=16),
            server_default="medio",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "commercial_call_handling",
            sa.String(length=32),
            server_default="declinar",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("human_transfer_rules", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("commercial_call_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("conversation_extra_rules", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "valid_assistant_conversation_style",
        "assistant_configs",
        "conversation_style IN ('natural', 'formal', 'comercial', 'breve')",
    )
    op.create_check_constraint(
        "valid_assistant_initiative_level",
        "assistant_configs",
        "initiative_level IN ('bajo', 'medio', 'alto')",
    )
    op.create_check_constraint(
        "valid_assistant_max_consecutive_questions",
        "assistant_configs",
        "max_consecutive_questions BETWEEN 1 AND 5",
    )
    op.create_check_constraint(
        "valid_assistant_commercial_call_handling",
        "assistant_configs",
        (
            "commercial_call_handling IN "
            "('declinar', 'transferir', 'responder_basico')"
        ),
    )


def downgrade() -> None:
    """Remove assistant conversation policy switches."""
    op.drop_constraint(
        "valid_assistant_commercial_call_handling",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_max_consecutive_questions",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_initiative_level",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_conversation_style",
        "assistant_configs",
        type_="check",
    )
    for column_name in (
        "conversation_extra_rules",
        "commercial_call_message",
        "human_transfer_rules",
        "commercial_call_handling",
        "initiative_level",
        "conversation_style",
        "max_consecutive_questions",
        "ask_service",
        "allow_price_answers",
        "allow_bookings",
    ):
        op.drop_column("assistant_configs", column_name)
