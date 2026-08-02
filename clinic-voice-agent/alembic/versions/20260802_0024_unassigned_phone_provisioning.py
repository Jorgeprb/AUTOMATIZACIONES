"""Allow purchasing a phone number before creating a clinic.

Revision ID: 20260802_0024
Revises: 20260730_0023
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_0024"
down_revision: str | None = "20260730_0023"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint(
        "phone_provisioning_orders_clinic_id_fkey",
        "phone_provisioning_orders",
        type_="foreignkey",
    )
    op.alter_column(
        "phone_provisioning_orders",
        "clinic_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.create_foreign_key(
        "phone_provisioning_orders_clinic_id_fkey",
        "phone_provisioning_orders",
        "clinics",
        ["clinic_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # A pre-clinic purchase has no representation in the previous schema.
    op.execute("DELETE FROM phone_provisioning_orders WHERE clinic_id IS NULL")
    op.drop_constraint(
        "phone_provisioning_orders_clinic_id_fkey",
        "phone_provisioning_orders",
        type_="foreignkey",
    )
    op.alter_column(
        "phone_provisioning_orders",
        "clinic_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_foreign_key(
        "phone_provisioning_orders_clinic_id_fkey",
        "phone_provisioning_orders",
        "clinics",
        ["clinic_id"],
        ["id"],
        ondelete="CASCADE",
    )
