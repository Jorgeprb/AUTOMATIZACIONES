"""SQLAlchemy domain models for clinics, calls, services, and appointments."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.db import Base


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    """Persist a string enum's values instead of its Python member names."""
    return [item.value for item in enum_type]


class UUIDPrimaryKeyMixin:
    """Provide a Python-generated UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Provide standard creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AppointmentStatus(StrEnum):
    """Lifecycle states for an appointment."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AppointmentSource(StrEnum):
    """Supported origins for an appointment."""

    VOICE_BOT = "voice_bot"
    ADMIN_PANEL = "admin_panel"


class CallStatus(StrEnum):
    """Lifecycle states for an inbound call."""

    INCOMING = "incoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    TRANSFERRED = "transferred"


class PhoneProvider(StrEnum):
    """Supported telephone-number providers."""

    VOIPSTUDIO = "voipstudio"
    TWILIO = "twilio"
    OTHER = "other"


class KnowledgeCategory(StrEnum):
    """Supported knowledge-base categories."""

    PRICES = "prices"
    SERVICES = "services"
    FAQ = "faq"
    POLICY = "policy"
    LOCATION = "location"
    INSURANCE = "insurance"
    CUSTOM = "custom"


class CallOutcome(StrEnum):
    """Business outcome detected after a call."""

    APPOINTMENT_CREATED = "appointment_created"
    CANCELLED = "cancelled"
    TRANSFERRED = "transferred"
    NO_ACTION = "no_action"
    FAILED = "failed"


class Clinic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant clinic using the voice assistant."""

    __tablename__ = "clinics"
    __table_args__ = (
        CheckConstraint(
            "data_retention_days BETWEEN 1 AND 3650",
            name="valid_data_retention_days",
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    default_language: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'es'"),
        default="es",
        nullable=False,
    )
    main_phone_number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
    )
    phone_number = synonym("main_phone_number")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_hours_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        default=dict,
        nullable=False,
    )
    emergency_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_retention_days: Mapped[int] = mapped_column(
        Integer,
        server_default=text("30"),
        default=30,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )

    workers: Mapped[list[Worker]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    services: Mapped[list[Service]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    google_credentials: Mapped[list[GoogleCredential]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    call_sessions: Mapped[list[CallSession]] = relationship(
        back_populates="clinic",
    )
    phone_numbers: Mapped[list[PhoneNumber]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    assistant_configs: Mapped[list[AssistantConfig]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    knowledge_items: Mapped[list[KnowledgeItem]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    conversation_flows: Mapped[list[ConversationFlow]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )
    test_sessions: Mapped[list[TestSession]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
    )


class PhoneNumber(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A telephone number routed to one clinic."""

    __tablename__ = "phone_numbers"
    __table_args__ = (
        UniqueConstraint("phone_number", name="uq_phone_numbers_phone_number"),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[PhoneProvider] = mapped_column(
        Enum(
            PhoneProvider,
            name="phone_provider",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=PhoneProvider.OTHER,
        server_default=PhoneProvider.OTHER.value,
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    sip_target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    clinic: Mapped[Clinic] = relationship(back_populates="phone_numbers")
    call_sessions: Mapped[list[CallSession]] = relationship(
        back_populates="phone_number",
    )


class Worker(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A clinic worker who can receive appointments."""

    __tablename__ = "workers"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "calendar_id",
            name="uq_workers_clinic_calendar",
        ),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendar_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    color_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    working_hours_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        default=dict,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="workers")
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="worker",
    )


class Service(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A bookable clinic service."""

    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes > 0",
            name="positive_duration",
        ),
        CheckConstraint(
            "buffer_before_minutes >= 0",
            name="nonnegative_buffer_before",
        ),
        CheckConstraint(
            "buffer_after_minutes >= 0",
            name="nonnegative_buffer_after",
        ),
        UniqueConstraint(
            "clinic_id",
            "name",
            name="uq_services_clinic_name",
        ),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    public_name: Mapped[str] = mapped_column(
        String(200),
        default=lambda context: str(context.get_current_parameters().get("name", "")),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        server_default=text("'EUR'"),
        default="EUR",
        nullable=False,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_before_minutes: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        default=0,
        nullable=False,
    )
    requires_worker: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    allowed_worker_ids: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    is_bookable_by_bot: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    buffer_after_minutes: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        default=0,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="services")
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="service",
    )


class AssistantConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned voice-assistant configuration for one clinic."""

    __tablename__ = "assistant_configs"
    __table_args__ = (
        Index(
            "uq_assistant_configs_one_active_per_clinic",
            "clinic_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        CheckConstraint(
            "conversation_retention_days BETWEEN 1 AND 3650",
            name="valid_retention_days",
        ),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    conversation_flow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation_flows.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    realtime_model: Mapped[str] = mapped_column(String(120), nullable=False)
    realtime_voice: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    temperature: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
    )
    first_message: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    safety_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    booking_policy_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cancellation_policy_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    transfer_policy_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    recording_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    conversation_retention_days: Mapped[int] = mapped_column(
        Integer,
        server_default=text("30"),
        default=30,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="assistant_configs")
    call_sessions: Mapped[list[CallSession]] = relationship(
        back_populates="assistant_config",
    )
    test_sessions: Mapped[list[TestSession]] = relationship(
        back_populates="assistant_config",
    )
    conversation_flow: Mapped[ConversationFlow | None] = relationship(
        back_populates="assistant_configs",
    )


class KnowledgeItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One reusable clinic fact supplied to the assistant."""

    __tablename__ = "knowledge_items"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[KnowledgeCategory] = mapped_column(
        Enum(
            KnowledgeCategory,
            name="knowledge_category",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        default=0,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="knowledge_items")


class ConversationFlow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurable structured conversation flow."""

    __tablename__ = "conversation_flows"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    flow_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        default=dict,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="conversation_flows")
    assistant_configs: Mapped[list[AssistantConfig]] = relationship(
        back_populates="conversation_flow",
    )


class TestSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persist one browser-based assistant conversation simulation."""

    __tablename__ = "test_sessions"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    assistant_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_configs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    use_real_calendar: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    messages_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        server_default=text("'[]'"),
        default=list,
        nullable=False,
    )
    state_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        default=dict,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="test_sessions")
    assistant_config: Mapped[AssistantConfig] = relationship(
        back_populates="test_sessions",
    )


class CallSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A telephone call handled by OpenAI Realtime."""

    __tablename__ = "call_sessions"
    __table_args__ = (Index("ix_call_sessions_openai_call_id", "openai_call_id"),)

    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinics.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phone_numbers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    assistant_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistant_configs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    openai_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    caller_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    caller_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    called_number: Mapped[str] = mapped_column(String(32), nullable=False)
    detected_intent: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )
    outcome: Mapped[CallOutcome | None] = mapped_column(
        Enum(
            CallOutcome,
            name="call_outcome",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        nullable=True,
    )
    recording_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    transcript_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    status: Mapped[CallStatus] = mapped_column(
        Enum(
            CallStatus,
            name="call_session_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=CallStatus.INCOMING,
        server_default=CallStatus.INCOMING.value,
        nullable=False,
    )
    conversation_state_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        default=dict,
        nullable=False,
    )
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="call_session",
    )
    clinic: Mapped[Clinic | None] = relationship(back_populates="call_sessions")
    phone_number: Mapped[PhoneNumber | None] = relationship(
        back_populates="call_sessions",
    )
    assistant_config: Mapped[AssistantConfig | None] = relationship(
        back_populates="call_sessions",
    )
    events: Mapped[list[CallEvent]] = relationship(
        back_populates="call_session",
        cascade="all, delete-orphan",
        order_by="CallEvent.created_at",
    )


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A patient appointment requested through the voice assistant."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="valid_time_range"),
        CheckConstraint(
            "reason IS NULL OR char_length(reason) <= 300",
            name="general_reason_length",
        ),
        Index(
            "ix_appointments_worker_schedule",
            "worker_id",
            "start_at",
            "end_at",
        ),
        Index("ix_appointments_patient_phone", "patient_phone"),
        UniqueConstraint(
            "google_calendar_id",
            "google_event_id",
            name="uq_appointments_google_event",
        ),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
    )
    google_calendar_id: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )
    google_event_id: Mapped[str] = mapped_column(String(256), nullable=False)
    patient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    patient_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            name="appointment_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=AppointmentStatus.PENDING,
        server_default=AppointmentStatus.PENDING.value,
        nullable=False,
    )
    source: Mapped[AppointmentSource] = mapped_column(
        Enum(
            AppointmentSource,
            name="appointment_source",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=AppointmentSource.VOICE_BOT,
        server_default=AppointmentSource.VOICE_BOT.value,
        nullable=False,
    )
    call_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="appointments")
    worker: Mapped[Worker] = relationship(back_populates="appointments")
    service: Mapped[Service | None] = relationship(back_populates="appointments")
    call_session: Mapped[CallSession | None] = relationship(
        back_populates="appointments",
    )


class CallEvent(UUIDPrimaryKeyMixin, Base):
    """An immutable event received or produced during a call."""

    __tablename__ = "call_events"

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        server_default=text("'{}'"),
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    call_session: Mapped[CallSession] = relationship(back_populates="events")


class GoogleCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Encrypted Google OAuth credentials owned by a clinic."""

    __tablename__ = "google_credentials"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            name="uq_google_credentials_clinic_id",
        ),
        UniqueConstraint(
            "clinic_id",
            "account_email",
            name="uq_google_credentials_clinic_account",
        ),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_json_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    clinic: Mapped[Clinic] = relationship(back_populates="google_credentials")
