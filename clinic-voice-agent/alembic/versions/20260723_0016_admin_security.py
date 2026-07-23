"""Add database-backed admin users, sessions, memberships, and audit logs.

Revision ID: 20260723_0016
Revises: 20260622_0015
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0016"
down_revision: str | None = "20260622_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("username", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="super_admin", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('super_admin','clinic_admin','operator','read_only')",
            name="ck_admin_users_admin_role",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_users"),
        sa.UniqueConstraint("username", name="uq_admin_users_username"),
    )
    op.create_table(
        "admin_memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="clinic_admin", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('super_admin','clinic_admin','operator','read_only')",
            name="ck_admin_memberships_admin_membership_role",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name="fk_admin_memberships_clinic_id_clinics", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["admin_users.id"], name="fk_admin_memberships_user_id_admin_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_memberships"),
        sa.UniqueConstraint(
            "user_id", "clinic_id", name="uq_admin_memberships_user_clinic"
        ),
    )
    op.create_index("ix_admin_memberships_clinic_id", "admin_memberships", ["clinic_id"])
    op.create_index("ix_admin_memberships_user_id", "admin_memberships", ["user_id"])

    op.create_table(
        "admin_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["admin_users.id"], name="fk_admin_sessions_user_id_admin_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"])
    op.create_index("ix_admin_sessions_expiry", "admin_sessions", ["expires_at"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("details_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name="fk_admin_audit_logs_clinic_id_clinics", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["admin_users.id"], name="fk_admin_audit_logs_user_id_admin_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_audit_logs"),
    )
    op.create_index("ix_admin_audit_created", "admin_audit_logs", ["created_at"])
    op.create_index("ix_admin_audit_user", "admin_audit_logs", ["user_id", "created_at"])
    op.create_index("ix_admin_audit_clinic", "admin_audit_logs", ["clinic_id", "created_at"])


def downgrade() -> None:
    op.drop_table("admin_audit_logs")
    op.drop_table("admin_sessions")
    op.drop_table("admin_memberships")
    op.drop_table("admin_users")
