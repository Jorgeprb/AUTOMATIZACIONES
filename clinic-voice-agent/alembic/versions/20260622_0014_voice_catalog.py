"""Add voice catalog table.

Revision ID: 20260622_0014
Revises: 20260622_0013
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0014"
down_revision: str | None = "20260622_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create provider-agnostic voice catalog."""
    op.alter_column(
        "assistant_configs",
        "tts_preview_voice",
        existing_type=sa.String(length=80),
        type_=sa.String(length=240),
        existing_nullable=True,
    )
    op.alter_column(
        "assistant_configs",
        "fallback_voice",
        existing_type=sa.String(length=80),
        type_=sa.String(length=240),
        existing_nullable=True,
    )
    op.create_table(
        "voice_catalog",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("voice_id", sa.String(length=240), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column(
            "supports_streaming",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "supports_telephony_codec",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "supports_voice_clone",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "requires_consent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "recommended",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "model",
            "voice_id",
            name="uq_voice_catalog_provider_model_voice",
        ),
    )
    op.create_index(
        "ix_voice_catalog_locale",
        "voice_catalog",
        ["locale"],
        unique=False,
    )
    op.create_index(
        "ix_voice_catalog_provider_enabled",
        "voice_catalog",
        ["provider", "enabled"],
        unique=False,
    )


def downgrade() -> None:
    """Drop provider-agnostic voice catalog."""
    op.drop_index("ix_voice_catalog_provider_enabled", table_name="voice_catalog")
    op.drop_index("ix_voice_catalog_locale", table_name="voice_catalog")
    op.drop_table("voice_catalog")
    op.alter_column(
        "assistant_configs",
        "fallback_voice",
        existing_type=sa.String(length=240),
        type_=sa.String(length=80),
        existing_nullable=True,
    )
    op.alter_column(
        "assistant_configs",
        "tts_preview_voice",
        existing_type=sa.String(length=240),
        type_=sa.String(length=80),
        existing_nullable=True,
    )
