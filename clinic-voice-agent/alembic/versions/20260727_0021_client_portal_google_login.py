"""Add client portal identities and short-lived Google login state.

Revision ID: 20260727_0021
Revises: 20260726_0020
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0021"
down_revision: str | None = "20260726_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("admin_users", sa.Column("avatar_url", sa.String(length=1000), nullable=True))
    op.add_column("admin_users", sa.Column("google_subject", sa.String(length=255), nullable=True))
    op.add_column(
        "admin_users",
        sa.Column("auth_provider", sa.String(length=32), server_default="password", nullable=False),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)
    op.create_unique_constraint("uq_admin_users_google_subject", "admin_users", ["google_subject"])

    op.create_table(
        "oauth_login_states",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("code_verifier", sa.String(length=256), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1000), nullable=False),
        sa.Column("portal", sa.String(length=24), nullable=False),
        sa.Column("return_to", sa.String(length=1000), server_default="/", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_login_states"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_login_states_state_hash"),
    )
    op.create_index("ix_oauth_login_states_expiry", "oauth_login_states", ["expires_at"])


def downgrade() -> None:
    op.drop_table("oauth_login_states")
    op.drop_constraint("uq_admin_users_google_subject", "admin_users", type_="unique")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_column("admin_users", "auth_provider")
    op.drop_column("admin_users", "google_subject")
    op.drop_column("admin_users", "avatar_url")
    op.drop_column("admin_users", "email")
