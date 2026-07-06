"""Add dual call audio architecture fields.

Revision ID: 20260622_0013
Revises: 20260622_0012
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0013"
down_revision: str | None = "20260622_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist call routing mode and external voice provider settings."""
    op.add_column(
        "assistant_configs",
        sa.Column(
            "call_audio_mode",
            sa.String(length=32),
            server_default="openai_hosted_sip",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "voice_provider",
            sa.String(length=32),
            server_default="openai",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("tts_model", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_id", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_locale", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_gender", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "voice_speed",
            sa.Numeric(4, 2),
            server_default="1.00",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "voice_pitch",
            sa.Numeric(5, 2),
            server_default="0.00",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_stability", sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_similarity", sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column("voice_temperature", sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "output_audio_format",
            sa.String(length=16),
            server_default="pcm16",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "telephony_codec",
            sa.String(length=16),
            server_default="pcmu",
            nullable=False,
        ),
    )
    op.add_column(
        "assistant_configs",
        sa.Column(
            "external_voice_legal_confirmed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "valid_assistant_call_audio_mode",
        "assistant_configs",
        "call_audio_mode IN ('openai_hosted_sip', 'vps_media_bridge')",
    )
    op.create_check_constraint(
        "valid_assistant_voice_provider",
        "assistant_configs",
        (
            "voice_provider IN ("
            "'openai', 'azure', 'google', 'elevenlabs', 'amazon_polly', "
            "'deepgram', 'cartesia', 'resemble', 'readspeaker', "
            "'acapela', 'cereproc', 'local_coqui', 'local_chatterbox', "
            "'custom_http')"
        ),
    )
    op.create_check_constraint(
        "valid_assistant_voice_speed",
        "assistant_configs",
        "voice_speed BETWEEN 0.25 AND 4.00",
    )
    op.create_check_constraint(
        "valid_assistant_voice_pitch",
        "assistant_configs",
        "voice_pitch BETWEEN -24.00 AND 24.00",
    )
    op.create_check_constraint(
        "valid_assistant_voice_stability",
        "assistant_configs",
        "voice_stability IS NULL OR voice_stability BETWEEN 0.00 AND 1.00",
    )
    op.create_check_constraint(
        "valid_assistant_voice_similarity",
        "assistant_configs",
        "voice_similarity IS NULL OR voice_similarity BETWEEN 0.00 AND 1.00",
    )
    op.create_check_constraint(
        "valid_assistant_voice_temperature",
        "assistant_configs",
        "voice_temperature IS NULL OR voice_temperature BETWEEN 0.00 AND 2.00",
    )
    op.create_check_constraint(
        "valid_assistant_output_audio_format",
        "assistant_configs",
        "output_audio_format IN ('pcm16', 'wav', 'mp3', 'opus')",
    )
    op.create_check_constraint(
        "valid_assistant_telephony_codec",
        "assistant_configs",
        "telephony_codec IN ('pcmu', 'pcma', 'pcm16')",
    )


def downgrade() -> None:
    """Remove dual call audio architecture fields."""
    for constraint_name in (
        "valid_assistant_telephony_codec",
        "valid_assistant_output_audio_format",
        "valid_assistant_voice_temperature",
        "valid_assistant_voice_similarity",
        "valid_assistant_voice_stability",
        "valid_assistant_voice_pitch",
        "valid_assistant_voice_speed",
        "valid_assistant_voice_provider",
        "valid_assistant_call_audio_mode",
    ):
        op.drop_constraint(constraint_name, "assistant_configs", type_="check")
    for column_name in (
        "external_voice_legal_confirmed",
        "telephony_codec",
        "output_audio_format",
        "voice_temperature",
        "voice_similarity",
        "voice_stability",
        "voice_pitch",
        "voice_speed",
        "voice_gender",
        "voice_locale",
        "voice_id",
        "tts_model",
        "voice_provider",
        "call_audio_mode",
    ):
        op.drop_column("assistant_configs", column_name)
