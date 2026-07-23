"""Add idempotency, overlap protection, webhook receipts and durable outbox.

Revision ID: 20260723_0017
Revises: 20260723_0016
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0017"
down_revision: str | None = "20260723_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.create_unique_constraint(
        "uq_appointments_clinic_idempotency",
        "appointments",
        ["clinic_id", "idempotency_key"],
    )
    # Database-level last line of defence against double booking. Service buffers
    # remain enforced in application logic because they are service-specific.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT ex_appointments_worker_active_overlap
        EXCLUDE USING gist (
          worker_id WITH =,
          tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status IN ('pending', 'confirmed'))
        """
    )
    op.create_unique_constraint(
        "uq_call_sessions_openai_call_id", "call_sessions", ["openai_call_id"]
    )
    op.create_table(
        "webhook_receipts",
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="processing", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_receipts"),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )
    op.create_index(
        "ix_webhook_receipts_status_created", "webhook_receipts", ["status", "created_at"]
    )
    op.create_table(
        "integration_outbox",
        sa.Column("kind", sa.String(120), nullable=False),
        sa.Column("dedupe_key", sa.String(240), nullable=False),
        sa.Column("payload_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_integration_outbox"),
        sa.UniqueConstraint("dedupe_key", name="uq_integration_outbox_dedupe"),
    )
    op.create_index(
        "ix_integration_outbox_pending", "integration_outbox", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_integration_outbox_pending", table_name="integration_outbox")
    op.drop_table("integration_outbox")
    op.drop_index("ix_webhook_receipts_status_created", table_name="webhook_receipts")
    op.drop_table("webhook_receipts")
    op.drop_constraint("uq_call_sessions_openai_call_id", "call_sessions", type_="unique")
    op.execute(
        "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_worker_active_overlap"
    )
    op.drop_constraint("uq_appointments_clinic_idempotency", "appointments", type_="unique")
    op.drop_column("appointments", "idempotency_key")
