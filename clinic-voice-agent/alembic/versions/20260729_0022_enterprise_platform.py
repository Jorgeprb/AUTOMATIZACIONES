"""Add tenant CRM, resources, analytics, autonomous accounts and billing.

Revision ID: 20260729_0022
Revises: 20260728_0020
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0022"
down_revision: str | None = "20260728_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PHONE_PRODUCT_ID = "11111111-1111-4111-8111-111111111111"
_PHONE_PRICE_ID = "11111111-1111-4111-8111-111111111112"
_MONTHLY_PRODUCT_ID = "22222222-2222-4222-8222-222222222221"
_MONTHLY_PRICE_ID = "22222222-2222-4222-8222-222222222222"


def _timestamps() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    # Authentication and commercial account ownership.
    op.add_column("admin_users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "billing_accounts",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("legal_name", sa.String(240), nullable=True),
        sa.Column("tax_id", sa.String(80), nullable=True),
        sa.Column("billing_address_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("billing_email", sa.String(320), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), server_default=sa.text("'free'"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["admin_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_accounts_owner_user_id", "billing_accounts", ["owner_user_id"])
    op.create_index("ix_billing_accounts_status", "billing_accounts", ["status"])
    op.create_index("ix_billing_accounts_stripe_customer_id", "billing_accounts", ["stripe_customer_id"], unique=True)
    op.create_table(
        "billing_account_members",
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(24), server_default=sa.text("'member'"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("billing_account_id", "user_id", name="uq_billing_account_member"),
    )
    op.create_index("ix_billing_account_members_billing_account_id", "billing_account_members", ["billing_account_id"])
    op.create_index("ix_billing_account_members_user_id", "billing_account_members", ["user_id"])
    op.add_column("clinics", sa.Column("billing_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_clinics_billing_account_id_billing_accounts", "clinics", "billing_accounts", ["billing_account_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_clinics_billing_account_id", "clinics", ["billing_account_id"])

    # Customer CRM and historical links.
    op.create_table(
        "clinic_customers",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_phone", sa.String(32), nullable=False),
        sa.Column("display_phone", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("custom_values_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("preferred_worker_id", sa.Uuid(), nullable=True),
        sa.Column("personalization_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("first_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preferred_worker_id"], ["workers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "normalized_phone", name="uq_clinic_customers_phone"),
    )
    op.create_index("ix_clinic_customers_clinic_name", "clinic_customers", ["clinic_id", "name"])
    op.create_index("ix_clinic_customers_clinic_active", "clinic_customers", ["clinic_id", "is_active"])
    op.create_index("ix_clinic_customers_clinic_last_contact", "clinic_customers", ["clinic_id", "last_contact_at"])
    op.create_table(
        "clinic_customer_field_definitions",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("options_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("field_type IN ('text','textarea','number','boolean','date','select')", name="ck_clinic_customer_field_definitions_valid_customer_field_type"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "key", name="uq_customer_fields_clinic_key"),
    )
    op.create_index("ix_customer_fields_clinic_sort", "clinic_customer_field_definitions", ["clinic_id", "sort_order"])
    for table in ("call_sessions", "appointments"):
        op.add_column(table, sa.Column("customer_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(f"fk_{table}_customer_id_clinic_customers", table, "clinic_customers", ["customer_id"], ["id"], ondelete="SET NULL")
        op.create_index(f"ix_{table}_customer_id", table, ["customer_id"])

    # Service language matching and known-customer behavior.
    op.add_column("services", sa.Column("aliases_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("services", sa.Column("common_phrases_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("services", sa.Column("keywords_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("services", sa.Column("disambiguation_instructions", sa.Text(), nullable=True))
    assistant_columns = (
        sa.Column("known_customer_name_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("known_customer_greeting_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("known_customer_greeting_template", sa.Text(), server_default=sa.text("'Ola, {customer_name}. En que podo axudarche?'"), nullable=False),
        sa.Column("known_customer_explanation_template", sa.Text(), server_default=sa.text("'Non te preocupes, non son vidente. Recoñecín o número porque estás na base de datos para ofrecerche unha atención máis personalizada.'"), nullable=False),
        sa.Column("remember_customer_after_booking", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("suggest_preferred_worker_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("ask_worker_preference_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    for column in assistant_columns:
        op.add_column("assistant_configs", column)

    # Resource capacity.
    op.create_table(
        "clinic_resources",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.String(48), server_default=sa.text("'other'"), nullable=False),
        sa.Column("capacity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("schedule_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("capacity > 0", name="ck_clinic_resources_positive_resource_capacity"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_clinic_resources_name"),
    )
    op.create_index("ix_clinic_resources_clinic_id", "clinic_resources", ["clinic_id"])
    op.create_table(
        "service_resource_requirements",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_service_resource_requirements_positive_resource_requirement_quantity"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["clinic_resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "resource_id", name="uq_service_resource_requirement"),
    )
    op.create_index("ix_service_resource_requirements_clinic_id", "service_resource_requirements", ["clinic_id"])
    op.create_index("ix_service_resource_requirements_service_id", "service_resource_requirements", ["service_id"])
    op.create_index("ix_service_resource_requirements_resource_id", "service_resource_requirements", ["resource_id"])
    op.create_table(
        "resource_reservations",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_resource_reservations_positive_reserved_resource_quantity"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["clinic_resources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", "resource_id", name="uq_appointment_resource_reservation"),
    )
    op.create_index("ix_resource_reservations_clinic_id", "resource_reservations", ["clinic_id"])
    op.create_index("ix_resource_reservations_appointment_id", "resource_reservations", ["appointment_id"])
    op.create_index("ix_resource_reservations_resource_id", "resource_reservations", ["resource_id"])
    op.create_index("ix_resource_reservations_window", "resource_reservations", ["resource_id", "start_at", "end_at"])

    # Appointment reporting states and post-call analysis.
    op.drop_constraint("ck_appointments_appointment_status", "appointments", type_="check")
    op.alter_column(
        "appointments",
        "status",
        existing_type=sa.String(length=9),
        type_=sa.String(length=11),
    )
    op.create_check_constraint("appointment_status", "appointments", "status IN ('pending','confirmed','cancelled','failed','completed','no_show','rescheduled')")
    op.create_table(
        "call_analyses",
        sa.Column("call_session_id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("sentiment_label", sa.String(16), server_default=sa.text("'unknown'"), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(4, 3), server_default=sa.text("0"), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), server_default=sa.text("0"), nullable=False),
        sa.Column("intent", sa.String(120), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=True),
        sa.Column("resolution_label", sa.String(160), nullable=True),
        sa.Column("urgency", sa.String(24), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("topics_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("friction_points_json", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("analysis_version", sa.String(32), server_default=sa.text("'v1'"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("sentiment_score BETWEEN -1 AND 1", name="ck_call_analyses_valid_sentiment_score"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_call_analyses_valid_analysis_confidence"),
        sa.CheckConstraint("sentiment_label IN ('positive','neutral','negative','mixed','unknown')", name="ck_call_analyses_valid_sentiment_label"),
        sa.ForeignKeyConstraint(["call_session_id"], ["call_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_session_id", name="uq_call_analysis_call"),
    )
    op.create_index("ix_call_analyses_clinic_id", "call_analyses", ["clinic_id"])

    # Extensible catalog and Stripe projections.
    op.create_table(
        "billing_products",
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_type", sa.String(32), nullable=False),
        sa.Column("ownership_type", sa.String(32), server_default=sa.text("'service'"), nullable=False),
        sa.Column("entitlement_code", sa.String(80), nullable=True),
        sa.Column("quantity_configurable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("stripe_product_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_billing_products_code"),
    )
    op.create_index("ix_billing_products_stripe_product_id", "billing_products", ["stripe_product_id"], unique=True)
    op.create_table(
        "billing_prices",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("unit_amount_minor", sa.Integer(), nullable=False),
        sa.Column("billing_type", sa.String(24), nullable=False),
        sa.Column("interval", sa.String(16), nullable=True),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("unit_amount_minor >= 0", name="ck_billing_prices_nonnegative_billing_price"),
        sa.ForeignKeyConstraint(["product_id"], ["billing_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_billing_prices_code"),
    )
    op.create_index("ix_billing_prices_product_id", "billing_prices", ["product_id"])
    op.create_index("ix_billing_prices_stripe_price_id", "billing_prices", ["stripe_price_id"], unique=True)
    op.create_table(
        "purchase_orders",
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("total_one_time_minor", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_recurring_minor", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_orders_billing_account_id", "purchase_orders", ["billing_account_id"])
    op.create_index("ix_purchase_orders_clinic_id", "purchase_orders", ["clinic_id"])
    op.create_index("ix_purchase_orders_account_created", "purchase_orders", ["billing_account_id", "created_at"])
    op.create_index("ix_purchase_orders_stripe_checkout_session_id", "purchase_orders", ["stripe_checkout_session_id"], unique=True)
    op.create_table(
        "purchase_order_items",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("price_id", sa.Uuid(), nullable=False),
        sa.Column("product_name_snapshot", sa.String(200), nullable=False),
        sa.Column("unit_amount_minor", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("billing_type", sa.String(24), nullable=False),
        sa.Column("stripe_price_id_snapshot", sa.String(255), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_items_positive_order_item_quantity"),
        sa.ForeignKeyConstraint(["order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["billing_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["price_id"], ["billing_prices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_order_items_order_id", "purchase_order_items", ["order_id"])
    op.create_table(
        "payment_records",
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(255), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(120), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["purchase_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_records_billing_account_id", "payment_records", ["billing_account_id"])
    op.create_index("ix_payment_records_clinic_id", "payment_records", ["clinic_id"])
    op.create_index("ix_payment_records_account_created", "payment_records", ["billing_account_id", "created_at"])
    op.create_index("ix_payment_records_stripe_payment_intent_id", "payment_records", ["stripe_payment_intent_id"], unique=True)
    op.create_index("ix_payment_records_stripe_invoice_id", "payment_records", ["stripe_invoice_id"], unique=True)
    op.create_table(
        "clinic_subscriptions",
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("price_id", sa.Uuid(), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=False),
        sa.Column("stripe_subscription_item_id", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["billing_products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["price_id"], ["billing_prices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_subscription_item_id", name="uq_clinic_subscriptions_stripe_subscription_item_id"),
    )
    op.create_index("ix_clinic_subscriptions_billing_account_id", "clinic_subscriptions", ["billing_account_id"])
    op.create_index("ix_clinic_subscriptions_clinic_id", "clinic_subscriptions", ["clinic_id"])
    op.create_index("ix_clinic_subscriptions_stripe_subscription_id", "clinic_subscriptions", ["stripe_subscription_id"], unique=True)
    op.create_index("ix_clinic_subscriptions_account_status", "clinic_subscriptions", ["billing_account_id", "status"])
    op.create_table(
        "phone_provisioning_orders",
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(48), server_default=sa.text("'paid_pending_provisioning'"), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("assigned_number", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(48), nullable=True),
        sa.Column("external_provider_id", sa.String(255), nullable=True),
        sa.Column("sip_target", sa.String(500), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["clinic_subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_phone_provisioning_orders_billing_account_id", "phone_provisioning_orders", ["billing_account_id"])
    op.create_index("ix_phone_provisioning_orders_clinic_id", "phone_provisioning_orders", ["clinic_id"])
    op.create_index("ix_phone_provisioning_status_created", "phone_provisioning_orders", ["status", "created_at"])
    op.create_table(
        "clinic_entitlements",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["clinic_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "code", name="uq_clinic_entitlement_code"),
    )
    op.create_index("ix_clinic_entitlements_clinic_id", "clinic_entitlements", ["clinic_id"])
    op.create_index("ix_clinic_entitlements_billing_account_id", "clinic_entitlements", ["billing_account_id"])
    op.add_column("phone_numbers", sa.Column("provisioning_order_id", sa.Uuid(), nullable=True))
    op.add_column("phone_numbers", sa.Column("clinic_subscription_id", sa.Uuid(), nullable=True))
    op.add_column("phone_numbers", sa.Column("external_provider_id", sa.String(255), nullable=True))
    op.create_foreign_key("fk_phone_numbers_provisioning_order", "phone_numbers", "phone_provisioning_orders", ["provisioning_order_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_phone_numbers_clinic_subscription", "phone_numbers", "clinic_subscriptions", ["clinic_subscription_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_phone_numbers_provisioning_order_id", "phone_numbers", ["provisioning_order_id"])
    op.create_index("ix_phone_numbers_clinic_subscription_id", "phone_numbers", ["clinic_subscription_id"])

    op.create_table(
        "auth_action_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_action_token_hash"),
    )
    op.create_index("ix_auth_action_tokens_user_id", "auth_action_tokens", ["user_id"])
    op.create_index("ix_auth_action_tokens_user_kind", "auth_action_tokens", ["user_id", "kind", "expires_at"])

    # Seed the catalog with stable application IDs; Stripe IDs are configured later.
    op.execute(sa.text("""
        INSERT INTO billing_products
            (id, code, name, description, product_type, ownership_type, entitlement_code, quantity_configurable, is_active)
        VALUES
            (:phone_product_id, 'autogal_phone_number', 'Número de teléfono Autogal',
             'Número de teléfono propiedad del cliente después de la compra.', 'one_time', 'permanent', 'phone_owned', true, true),
            (:monthly_product_id, 'autogal_monthly_service', 'Servicio mensual Autogal',
             'Servicio mensual de asistente de voz por número o licencia.', 'subscription', 'service', 'assistant_production', true, true)
        ON CONFLICT (code) DO NOTHING
    """).bindparams(
        sa.bindparam("phone_product_id", _PHONE_PRODUCT_ID, type_=sa.Uuid()),
        sa.bindparam("monthly_product_id", _MONTHLY_PRODUCT_ID, type_=sa.Uuid()),
    ))
    op.execute(sa.text("""
        INSERT INTO billing_prices
            (id, product_id, code, currency, unit_amount_minor, billing_type, interval, is_active)
        VALUES
            (:phone_price_id, :phone_product_id, 'autogal_phone_eur_15', 'EUR', 1500, 'one_time', NULL, true),
            (:monthly_price_id, :monthly_product_id, 'autogal_monthly_eur_50', 'EUR', 5000, 'recurring', 'month', true)
        ON CONFLICT (code) DO NOTHING
    """).bindparams(
        sa.bindparam("phone_price_id", _PHONE_PRICE_ID, type_=sa.Uuid()),
        sa.bindparam("phone_product_id", _PHONE_PRODUCT_ID, type_=sa.Uuid()),
        sa.bindparam("monthly_price_id", _MONTHLY_PRICE_ID, type_=sa.Uuid()),
        sa.bindparam("monthly_product_id", _MONTHLY_PRODUCT_ID, type_=sa.Uuid()),
    ))


def downgrade() -> None:
    op.drop_index("ix_auth_action_tokens_user_kind", table_name="auth_action_tokens")
    op.drop_index("ix_auth_action_tokens_user_id", table_name="auth_action_tokens")
    op.drop_table("auth_action_tokens")
    op.drop_index("ix_phone_numbers_clinic_subscription_id", table_name="phone_numbers")
    op.drop_constraint("uq_phone_numbers_provisioning_order_id", "phone_numbers", type_="unique")
    op.drop_constraint("fk_phone_numbers_clinic_subscription", "phone_numbers", type_="foreignkey")
    op.drop_constraint("fk_phone_numbers_provisioning_order", "phone_numbers", type_="foreignkey")
    op.drop_column("phone_numbers", "external_provider_id")
    op.drop_column("phone_numbers", "clinic_subscription_id")
    op.drop_column("phone_numbers", "provisioning_order_id")
    for table in (
        "clinic_entitlements", "phone_provisioning_orders", "clinic_subscriptions",
        "payment_records", "purchase_order_items", "purchase_orders", "billing_prices",
        "billing_products", "call_analyses", "resource_reservations",
        "service_resource_requirements", "clinic_resources",
    ):
        op.drop_table(table)
    op.drop_constraint("appointment_status", "appointments", type_="check")
    op.alter_column(
        "appointments",
        "status",
        existing_type=sa.String(length=11),
        type_=sa.String(length=9),
    )
    op.create_check_constraint("ck_appointments_appointment_status", "appointments", "status IN ('pending','confirmed','cancelled','failed')")
    for name in (
        "ask_worker_preference_enabled", "suggest_preferred_worker_enabled",
        "remember_customer_after_booking", "known_customer_explanation_template",
        "known_customer_greeting_template", "known_customer_greeting_enabled",
        "known_customer_name_enabled",
    ):
        op.drop_column("assistant_configs", name)
    for name in ("disambiguation_instructions", "keywords_json", "common_phrases_json", "aliases_json"):
        op.drop_column("services", name)
    for table in ("appointments", "call_sessions"):
        op.drop_index(f"ix_{table}_customer_id", table_name=table)
        op.drop_constraint(f"fk_{table}_customer_id_clinic_customers", table, type_="foreignkey")
        op.drop_column(table, "customer_id")
    op.drop_table("clinic_customer_field_definitions")
    op.drop_table("clinic_customers")
    op.drop_index("ix_clinics_billing_account_id", table_name="clinics")
    op.drop_constraint("fk_clinics_billing_account_id_billing_accounts", "clinics", type_="foreignkey")
    op.drop_column("clinics", "billing_account_id")
    op.drop_table("billing_account_members")
    op.drop_table("billing_accounts")
    op.drop_column("admin_users", "email_verified_at")
