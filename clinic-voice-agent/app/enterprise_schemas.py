"""Schemas for CRM, analytics, commercial accounts and billing."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.customer_service import validate_field_key


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


CustomerFieldType = Literal["text", "textarea", "number", "boolean", "date", "select"]


class CustomerFieldDefinitionPayload(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    field_type: CustomerFieldType
    options_json: list[str] = Field(default_factory=list, max_length=100)
    required: bool = False
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return validate_field_key(value)

    @model_validator(mode="after")
    def validate_options(self) -> CustomerFieldDefinitionPayload:
        if self.field_type == "select" and not self.options_json:
            raise ValueError("Los campos select necesitan opciones.")
        if self.field_type != "select" and self.options_json:
            raise ValueError("Solo los campos select admiten opciones.")
        self.options_json = list(
            dict.fromkeys(item.strip() for item in self.options_json if item.strip())
        )
        return self


class CustomerFieldDefinitionRead(CustomerFieldDefinitionPayload, ORMModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ClinicCustomerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    notes: str | None = Field(default=None, max_length=20_000)
    custom_values_json: dict[str, Any] = Field(default_factory=dict)
    preferred_worker_id: uuid.UUID | None = None
    personalization_enabled: bool = True
    is_active: bool = True


class ClinicCustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=3, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    notes: str | None = Field(default=None, max_length=20_000)
    custom_values_json: dict[str, Any] | None = None
    preferred_worker_id: uuid.UUID | None = None
    personalization_enabled: bool | None = None
    is_active: bool | None = None


class ClinicCustomerRead(ORMModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    name: str
    normalized_phone: str
    display_phone: str
    email: str | None
    notes: str | None
    custom_values_json: dict[str, Any]
    preferred_worker_id: uuid.UUID | None
    personalization_enabled: bool
    is_active: bool
    first_contact_at: datetime | None
    last_contact_at: datetime | None
    anonymized_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerMergeRequest(BaseModel):
    source_customer_id: uuid.UUID
    target_customer_id: uuid.UUID


class CustomerImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


class RelatedAppointmentRead(ORMModel):
    id: uuid.UUID
    patient_name: str
    patient_phone: str
    start_at: datetime
    end_at: datetime
    status: str
    worker_id: uuid.UUID
    service_id: uuid.UUID | None


class RelatedCallRead(ORMModel):
    id: uuid.UUID
    caller_name: str | None
    caller_phone: str
    status: str
    outcome: str
    started_at: datetime
    ended_at: datetime | None
    summary_text: str | None


class CustomerDetail(ClinicCustomerRead):
    appointments: list[RelatedAppointmentRead] = Field(default_factory=list)
    calls: list[RelatedCallRead] = Field(default_factory=list)


class ResourcePayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    resource_type: str = Field(default="other", min_length=1, max_length=48)
    capacity: int = Field(default=1, ge=1, le=1000)
    schedule_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ResourceRead(ResourcePayload, ORMModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ResourceRequirementPayload(BaseModel):
    resource_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=1000)


class AnalyticsFilter(BaseModel):
    date_from: datetime
    date_to: datetime
    worker_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    phone_number: str | None = None
    appointment_status: str | None = None


class MetricPoint(BaseModel):
    key: str
    label: str
    value: float


class ClinicAnalyticsResponse(BaseModel):
    appointments_created: int
    appointments_cancelled: int
    appointments_completed: int
    appointments_no_show: int
    cancellation_rate: float
    call_to_booking_conversion: float
    estimated_revenue_minor: int
    calls_answered: int
    calls_failed: int
    average_call_duration_seconds: float
    new_customers: int
    returning_customers: int
    appointments_by_service: list[MetricPoint]
    appointments_by_worker: list[MetricPoint]
    appointments_by_weekday: list[MetricPoint]
    appointments_by_hour: list[MetricPoint]
    appointment_statuses: list[MetricPoint]
    sentiments: list[MetricPoint]
    timeline: list[MetricPoint]
    heatmap: list[dict[str, int | str]]


class GlobalAnalyticsResponse(BaseModel):
    clinics: int
    contracted_numbers: int
    active_subscriptions: int
    mrr_minor: int
    failed_payments: int
    pending_provisioning: int
    appointments: int
    calls: int


class CallAnalysisRead(ORMModel):
    id: uuid.UUID
    call_session_id: uuid.UUID
    clinic_id: uuid.UUID
    sentiment_label: str
    sentiment_score: float
    confidence: float
    intent: str | None
    resolved: bool | None
    resolution_label: str | None
    urgency: str
    topics_json: list[str]
    friction_points_json: list[str]
    summary: str | None
    analyzed_at: datetime | None
    model: str | None
    analysis_version: str
    error: str | None


class BillingAccountPayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    tax_id: str | None = Field(default=None, max_length=80)
    billing_email: str = Field(min_length=3, max_length=320)
    billing_address_json: dict[str, Any] = Field(default_factory=dict)


class BillingAccountRead(BillingAccountPayload, ORMModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    stripe_customer_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    clinic_count: int = 0
    user_count: int = 0
    owner_email: str | None = None
    owner_name: str | None = None


class BillingProductPayload(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    product_type: Literal["one_time", "subscription", "addon"]
    ownership_type: Literal["permanent", "service"] = "service"
    entitlement_code: str | None = Field(default=None, max_length=80)
    quantity_configurable: bool = True
    stripe_product_id: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class BillingProductRead(BillingProductPayload, ORMModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BillingPricePayload(BaseModel):
    product_id: uuid.UUID
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    unit_amount_minor: int = Field(ge=0)
    billing_type: Literal["one_time", "recurring"]
    interval: Literal["month", "year"] | None = None
    stripe_price_id: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_interval(self) -> BillingPricePayload:
        if self.billing_type == "recurring" and not self.interval:
            raise ValueError("Los precios recurrentes necesitan intervalo.")
        if self.billing_type == "one_time" and self.interval:
            raise ValueError("Un pago único no puede tener intervalo.")
        return self


class BillingPriceRead(BillingPricePayload, ORMModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CatalogItem(BaseModel):
    product: BillingProductRead
    prices: list[BillingPriceRead]


class CheckoutLine(BaseModel):
    price_id: uuid.UUID
    quantity: int = Field(ge=1, le=100)


class CheckoutRequest(BaseModel):
    clinic_id: uuid.UUID
    lines: list[CheckoutLine] = Field(min_length=1, max_length=20)


class CheckoutResponse(BaseModel):
    order_id: uuid.UUID
    checkout_url: str


class OrderRead(ORMModel):
    id: uuid.UUID
    billing_account_id: uuid.UUID
    clinic_id: uuid.UUID | None
    status: str
    currency: str
    total_one_time_minor: int
    total_recurring_minor: int
    stripe_checkout_session_id: str | None
    checkout_url: str | None
    created_at: datetime


class SubscriptionRead(ORMModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    status: str
    quantity: int
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None


class PaymentRead(ORMModel):
    id: uuid.UUID
    clinic_id: uuid.UUID | None
    amount_minor: int
    currency: str
    status: str
    paid_at: datetime | None
    failure_code: str | None
    created_at: datetime


class ProvisioningRead(ORMModel):
    id: uuid.UUID
    billing_account_id: uuid.UUID
    clinic_id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    subscription_id: uuid.UUID | None
    status: str
    quantity: int
    assigned_number: str | None
    provider: str | None
    external_provider_id: str | None
    sip_target: str | None
    webhook_url: str | None
    notes: str | None
    provisioned_at: datetime | None
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProvisioningUpdate(BaseModel):
    assigned_number: str | None = Field(default=None, max_length=32)
    provider: str | None = Field(default=None, max_length=48)
    external_provider_id: str | None = Field(default=None, max_length=255)
    sip_target: str | None = Field(default=None, max_length=500)
    webhook_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    status: (
        Literal["paid_pending_provisioning", "provisioned", "active", "failed"] | None
    ) = None


class EntitlementRead(ORMModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    code: str
    status: str
    quantity: int
    starts_at: datetime | None
    ends_at: datetime | None
    metadata_json: dict[str, Any]


class CommercialSummary(BaseModel):
    account: BillingAccountRead | None
    orders: list[OrderRead]
    subscriptions: list[SubscriptionRead]
    payments: list[PaymentRead]
    provisioning: list[ProvisioningRead]
    entitlements: list[EntitlementRead]
    phone_numbers: list[str]
    can_use_production: bool


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=1024)
    repeat_password: str = Field(min_length=10, max_length=1024)
    accepted_terms: bool
    accepted_privacy: bool

    @model_validator(mode="after")
    def validate_registration(self) -> RegisterRequest:
        if self.password != self.repeat_password:
            raise ValueError("Las contraseñas no coinciden.")
        if not self.accepted_terms or not self.accepted_privacy:
            raise ValueError("Debes aceptar los términos y la privacidad.")
        if (
            not any(ch.islower() for ch in self.password)
            or not any(ch.isupper() for ch in self.password)
            or not any(ch.isdigit() for ch in self.password)
        ):
            raise ValueError("La contraseña necesita mayúscula, minúscula y número.")
        return self


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class PasswordResetRequest(TokenRequest):
    password: str = Field(min_length=10, max_length=1024)
    repeat_password: str = Field(min_length=10, max_length=1024)

    @model_validator(mode="after")
    def passwords_match(self) -> PasswordResetRequest:
        if self.password != self.repeat_password:
            raise ValueError("Las contraseñas no coinciden.")
        if (
            not any(ch.islower() for ch in self.password)
            or not any(ch.isupper() for ch in self.password)
            or not any(ch.isdigit() for ch in self.password)
        ):
            raise ValueError("La contraseña necesita mayúscula, minúscula y número.")
        return self


class OnboardingClinicRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="Europe/Madrid", max_length=64)
    main_phone_number: str = Field(default="pending", min_length=3, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=1000)
