"""Add assistant voice profile fields.

Revision ID: 20260622_0012
Revises: 20260622_0011
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0012"
down_revision: str | None = "20260622_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist advanced voice profile settings for each assistant."""
    op.add_column(
        "assistant_configs",
        sa.Column("voice_instructions", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_preset", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("tts_preview_voice", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("fallback_voice", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "speech_speed",
            sa.String(length=16),
            server_default="normal",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "pause_style",
            sa.String(length=16),
            server_default="natural",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "phone_reading_style",
            sa.String(length=16),
            server_default="groups",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "date_reading_style",
            sa.String(length=16),
            server_default="natural",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "price_reading_style",
            sa.String(length=16),
            server_default="clear",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "allow_interruptions",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("idle_timeout_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "ai_disclosure_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("ai_disclosure_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "preview_audio_format",
            sa.String(length=16),
            server_default="mp3",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_speech_speed",
        "assistant_configs",
        "speech_speed IN ('slow', 'normal', 'fast')",
    )
    op.create_check_constraint(
        "valid_assistant_pause_style",
        "assistant_configs",
        "pause_style IN ('short', 'natural', 'slow')",
    )
    op.create_check_constraint(
        "valid_assistant_phone_reading_style",
        "assistant_configs",
        "phone_reading_style IN ('digits', 'groups', 'natural')",
    )
    op.create_check_constraint(
        "valid_assistant_date_reading_style",
        "assistant_configs",
        "date_reading_style IN ('natural', 'numeric')",
    )
    op.create_check_constraint(
        "valid_assistant_price_reading_style",
        "assistant_configs",
        "price_reading_style IN ('brief', 'clear', 'detailed')",
    )
    op.create_check_constraint(
        "valid_assistant_preview_audio_format",
        "assistant_configs",
        "preview_audio_format IN ('mp3', 'wav', 'opus')",
    )
    op.create_check_constraint(
        "valid_assistant_idle_timeout_ms",
        "assistant_configs",
        "idle_timeout_ms IS NULL OR idle_timeout_ms BETWEEN 1000 AND 60000",
    )


def downgrade() -> None:
    """Remove advanced voice profile settings."""
    op.drop_constraint(
        "valid_assistant_idle_timeout_ms",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_preview_audio_format",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_price_reading_style",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_date_reading_style",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_phone_reading_style",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_pause_style",
        "assistant_configs",
        type_="check",
    )
    op.drop_constraint(
        "valid_assistant_speech_speed",
        "assistant_configs",
        type_="check",
    )
    for column_name in (
        "preview_audio_format",
        "ai_disclosure_message",
        "ai_disclosure_enabled",
        "idle_timeout_ms",
        "allow_interruptions",
        "price_reading_style",
        "date_reading_style",
        "phone_reading_style",
        "pause_style",
        "speech_speed",
        "fallback_voice",
        "tts_preview_voice",
        "voice_preset",
        "voice_instructions",
    ):
        op.drop_column("assistant_configs", column_name)
