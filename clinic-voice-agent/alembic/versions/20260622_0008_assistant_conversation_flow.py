"""Associate assistant configurations with conversation flows.

Revision ID: 20260622_0008
Revises: 20260622_0007
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0008"
down_revision: str | None = "20260622_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the optional flow foreign key to assistant configurations."""
    op.add_column(
        "assistant_configs",
        sa.Column("conversation_flow_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_assistant_configs_conversation_flow_id"),
        "assistant_configs",
        ["conversation_flow_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f(
            "fk_assistant_configs_conversation_flow_id_conversation_flows"
        ),
        "assistant_configs",
        "conversation_flows",
        ["conversation_flow_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove the assistant-flow association."""
    op.drop_constraint(
        op.f(
            "fk_assistant_configs_conversation_flow_id_conversation_flows"
        ),
        "assistant_configs",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_assistant_configs_conversation_flow_id"),
        table_name="assistant_configs",
    )
    op.drop_column("assistant_configs", "conversation_flow_id")
