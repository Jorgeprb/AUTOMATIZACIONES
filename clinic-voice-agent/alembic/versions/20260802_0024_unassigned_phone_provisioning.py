"""Allow purchasing a phone number before creating a clinic.

Revision ID: 20260802_0024
Revises: 20260730_0023

The original ``phone_provisioning_orders.clinic_id`` foreign key was created
without an explicit constraint name. PostgreSQL, SQLAlchemy naming conventions,
and databases upgraded through older project revisions may therefore expose a
different name. This migration discovers the real FK from PostgreSQL's catalog
instead of assuming a generated name.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "20260802_0024"
down_revision: str | None = "20260730_0023"
branch_labels: str | None = None
depends_on: str | None = None


_DROP_CLINIC_FOREIGN_KEYS_SQL = sa.text(
    """
    DO $$
    DECLARE
        fk_record record;
    BEGIN
        FOR fk_record IN
            SELECT
                namespace.nspname AS schema_name,
                constraint_row.conname AS constraint_name
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS source_table
              ON source_table.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = source_table.relnamespace
            JOIN pg_class AS target_table
              ON target_table.oid = constraint_row.confrelid
            JOIN pg_attribute AS source_column
              ON source_column.attrelid = source_table.oid
             AND source_column.attnum = constraint_row.conkey[1]
            WHERE constraint_row.contype = 'f'
              AND source_table.relname = 'phone_provisioning_orders'
              AND target_table.relname = 'clinics'
              AND source_column.attname = 'clinic_id'
              AND array_length(constraint_row.conkey, 1) = 1
              AND namespace.nspname = current_schema()
        LOOP
            EXECUTE format(
                'ALTER TABLE %I.%I DROP CONSTRAINT %I',
                fk_record.schema_name,
                'phone_provisioning_orders',
                fk_record.constraint_name
            );
        END LOOP;
    END
    $$
    """
)


def _drop_existing_clinic_foreign_keys() -> None:
    """Drop the clinic FK regardless of the name used in the live database."""

    op.execute(_DROP_CLINIC_FOREIGN_KEYS_SQL)


def upgrade() -> None:
    _drop_existing_clinic_foreign_keys()
    op.alter_column(
        "phone_provisioning_orders",
        "clinic_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_phone_provisioning_orders_clinic_id_clinics",
        "phone_provisioning_orders",
        "clinics",
        ["clinic_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # A pre-clinic purchase has no representation in the previous schema.
    op.execute("DELETE FROM phone_provisioning_orders WHERE clinic_id IS NULL")
    _drop_existing_clinic_foreign_keys()
    op.alter_column(
        "phone_provisioning_orders",
        "clinic_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_phone_provisioning_orders_clinic_id_clinics",
        "phone_provisioning_orders",
        "clinics",
        ["clinic_id"],
        ["id"],
        ondelete="CASCADE",
    )
