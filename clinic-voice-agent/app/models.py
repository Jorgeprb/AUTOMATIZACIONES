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
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


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
    billing_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
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
    provisioning_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phone_provisioning_orders.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    clinic_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinic_subscriptions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    external_provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
    inherit_clinic_hours: Mapped[bool] = mapped_column(
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
    aliases_json: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'"), default=list, nullable=False
    )
    common_phrases_json: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'"), default=list, nullable=False
    )
    keywords_json: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'"), default=list, nullable=False
    )
    disambiguation_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        CheckConstraint(
            "max_proposed_slots BETWEEN 1 AND 10",
            name="valid_assistant_max_proposed_slots",
        ),
        CheckConstraint(
            "service_prompt_mode IN ('list_services', 'ask_open', 'infer_confirm')",
            name="valid_assistant_service_prompt_mode",
        ),
        CheckConstraint(
            "slot_interval_minutes IN (5, 10, 15, 20, 30, 60)",
            name="valid_assistant_slot_interval_minutes",
        ),
        CheckConstraint(
            ("conversation_style IN ('natural', 'formal', 'comercial', 'breve')"),
            name="valid_assistant_conversation_style",
        ),
        CheckConstraint(
            "initiative_level IN ('bajo', 'medio', 'alto')",
            name="valid_assistant_initiative_level",
        ),
        CheckConstraint(
            "max_consecutive_questions BETWEEN 1 AND 5",
            name="valid_assistant_max_consecutive_questions",
        ),
        CheckConstraint(
            (
                "commercial_call_handling IN "
                "('declinar', 'transferir', 'responder_basico')"
            ),
            name="valid_assistant_commercial_call_handling",
        ),
        CheckConstraint(
            "speech_speed IN ('slow', 'normal', 'fast')",
            name="valid_assistant_speech_speed",
        ),
        CheckConstraint(
            "pause_style IN ('short', 'natural', 'slow')",
            name="valid_assistant_pause_style",
        ),
        CheckConstraint(
            "phone_reading_style IN ('digits', 'groups', 'natural')",
            name="valid_assistant_phone_reading_style",
        ),
        CheckConstraint(
            "date_reading_style IN ('natural', 'numeric')",
            name="valid_assistant_date_reading_style",
        ),
        CheckConstraint(
            "price_reading_style IN ('brief', 'clear', 'detailed')",
            name="valid_assistant_price_reading_style",
        ),
        CheckConstraint(
            "preview_audio_format IN ('mp3', 'wav', 'opus')",
            name="valid_assistant_preview_audio_format",
        ),
        CheckConstraint(
            "idle_timeout_ms IS NULL OR idle_timeout_ms BETWEEN 1000 AND 60000",
            name="valid_assistant_idle_timeout_ms",
        ),
        CheckConstraint(
            "turn_end_silence_ms BETWEEN 200 AND 1200",
            name="valid_assistant_turn_end_silence_ms",
        ),
        CheckConstraint(
            "call_audio_mode IN ('openai_hosted_sip', 'vps_media_bridge')",
            name="valid_assistant_call_audio_mode",
        ),
        CheckConstraint(
            (
                "voice_provider IN ("
                "'openai', 'azure', 'google', 'elevenlabs', 'amazon_polly', "
                "'deepgram', 'cartesia', 'resemble', 'readspeaker', "
                "'acapela', 'cereproc', 'local_coqui', 'local_chatterbox', "
                "'custom_http')"
            ),
            name="valid_assistant_voice_provider",
        ),
        CheckConstraint(
            "voice_speed BETWEEN 0.50 AND 2.00",
            name="valid_assistant_voice_speed",
        ),
        CheckConstraint(
            "voice_pitch BETWEEN -24.00 AND 24.00",
            name="valid_assistant_voice_pitch",
        ),
        CheckConstraint(
            "voice_stability IS NULL OR voice_stability BETWEEN 0.00 AND 1.00",
            name="valid_assistant_voice_stability",
        ),
        CheckConstraint(
            "voice_similarity IS NULL OR voice_similarity BETWEEN 0.00 AND 1.00",
            name="valid_assistant_voice_similarity",
        ),
        CheckConstraint(
            "voice_temperature IS NULL OR voice_temperature BETWEEN 0.00 AND 2.00",
            name="valid_assistant_voice_temperature",
        ),
        CheckConstraint(
            "output_audio_format IN ('pcm16', 'wav', 'mp3', 'opus')",
            name="valid_assistant_output_audio_format",
        ),
        CheckConstraint(
            "telephony_codec IN ('pcmu', 'pcma', 'pcm16')",
            name="valid_assistant_telephony_codec",
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
    call_audio_mode: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'openai_hosted_sip'"),
        default="openai_hosted_sip",
        nullable=False,
    )
    voice_provider: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'openai'"),
        default="openai",
        nullable=False,
    )
    tts_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    voice_locale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voice_gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    azure_speech_region: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    voice_style: Mapped[str | None] = mapped_column(String(80), nullable=True)
    voice_speed: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        server_default=text("1.00"),
        default=Decimal("1.00"),
        nullable=False,
    )
    voice_pitch: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        server_default=text("0.00"),
        default=Decimal("0.00"),
        nullable=False,
    )
    voice_stability: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2),
        nullable=True,
    )
    voice_similarity: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2),
        nullable=True,
    )
    voice_temperature: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2),
        nullable=True,
    )
    output_audio_format: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'pcm16'"),
        default="pcm16",
        nullable=False,
    )
    telephony_codec: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'pcmu'"),
        default="pcmu",
        nullable=False,
    )
    external_voice_legal_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    voice_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_preset: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tts_preview_voice: Mapped[str | None] = mapped_column(String(240), nullable=True)
    fallback_voice: Mapped[str | None] = mapped_column(String(240), nullable=True)
    speech_speed: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'normal'"),
        default="normal",
        nullable=False,
    )
    pause_style: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'natural'"),
        default="natural",
        nullable=False,
    )
    phone_reading_style: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'groups'"),
        default="groups",
        nullable=False,
    )
    date_reading_style: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'natural'"),
        default="natural",
        nullable=False,
    )
    price_reading_style: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'clear'"),
        default="clear",
        nullable=False,
    )
    time_reading_style: Mapped[str] = mapped_column(
        String(24),
        default="natural_quarters",
        nullable=False,
    )
    caller_phone_policy: Mapped[str] = mapped_column(
        String(24),
        default="ask_before_use",
        nullable=False,
    )
    calendar_event_title_template: Mapped[str] = mapped_column(
        Text,
        default="Cita - {patient_name}",
        nullable=False,
    )
    calendar_event_description_template: Mapped[str] = mapped_column(
        Text,
        default=(
            "Reserva creada por asistente telefónico.\n"
            "Paciente: {patient_name}\n"
            "Teléfono: {patient_phone}\n"
            "Servicio: {service_name}\n"
            "Profesional: {worker_name}\n"
            "Fecha: {start_date}\n"
            "Hora: {start_time}\n"
            "Motivo general: {reason}"
        ),
        nullable=False,
    )

    known_customer_name_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    known_customer_greeting_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    known_customer_greeting_template: Mapped[str] = mapped_column(
        Text,
        server_default=text("'Ola, {customer_name}. En que podo axudarche?'"),
        default="Ola, {customer_name}. En que podo axudarche?",
        nullable=False,
    )
    known_customer_explanation_template: Mapped[str] = mapped_column(
        Text,
        server_default=text(
            "'Non te preocupes, non son vidente. Recoñecín o número porque estás na base de datos para ofrecerche unha atención máis personalizada.'"
        ),
        default=(
            "Non te preocupes, non son vidente. Recoñecín o número porque estás "
            "na base de datos para ofrecerche unha atención máis personalizada."
        ),
        nullable=False,
    )
    remember_customer_after_booking: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    suggest_preferred_worker_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    ask_worker_preference_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )

    allow_interruptions: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    idle_timeout_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_end_silence_ms: Mapped[int] = mapped_column(
        Integer,
        server_default=text("350"),
        default=350,
        nullable=False,
    )
    ai_disclosure_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    ai_disclosure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_audio_format: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'mp3'"),
        default="mp3",
        nullable=False,
    )
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
    tone: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'profesional'"),
        default="profesional",
        nullable=False,
    )
    response_length: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'normal'"),
        default="normal",
        nullable=False,
    )
    ask_patient_name: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    ask_patient_phone: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    ask_general_reason: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    allow_booking_without_worker: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    allow_bookings: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    allow_price_answers: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    ask_service: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    service_prompt_mode: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'ask_open'"),
        default="ask_open",
        nullable=False,
    )
    slot_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        server_default=text("15"),
        default=15,
        nullable=False,
    )
    direct_availability_response: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    direct_booking_response: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    booking_confirmation_datetime_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    post_booking_followup_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    post_booking_followup_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    hangup_after_no_more_help: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    hangup_on_natural_goodbye: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    max_proposed_slots: Mapped[int] = mapped_column(
        Integer,
        server_default=text("3"),
        default=3,
        nullable=False,
    )
    max_consecutive_questions: Mapped[int] = mapped_column(
        Integer,
        server_default=text("2"),
        default=2,
        nullable=False,
    )
    conversation_style: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'natural'"),
        default="natural",
        nullable=False,
    )
    initiative_level: Mapped[str] = mapped_column(
        String(16),
        server_default=text("'medio'"),
        default="medio",
        nullable=False,
    )
    commercial_call_handling: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'declinar'"),
        default="declinar",
        nullable=False,
    )
    allow_cancellations: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    allow_reschedules: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    natural_confirmation_required: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    avoid_exact_confirmation_phrases: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    additional_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    forbidden_phrases: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_availability_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_calendar_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_transfer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_transfer_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    commercial_call_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_extra_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    closing_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_prices: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    use_knowledge_base: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    strict_calendar_mode: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    transcript_enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
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


class VoiceCatalog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Selectable voice/model options exposed by provider adapters."""

    __tablename__ = "voice_catalog"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            "voice_id",
            name="uq_voice_catalog_provider_model_voice",
        ),
        Index("ix_voice_catalog_provider_enabled", "provider", "enabled"),
        Index("ix_voice_catalog_locale", "locale"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(240), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    locale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    supports_telephony_codec: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    supports_voice_clone: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    requires_consent: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    recommended: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        default=False,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
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
    source_type: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'manual'"),
        default="manual",
        nullable=False,
    )
    source: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    import_status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'manual'"),
        default="manual",
        nullable=False,
    )
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
    __table_args__ = (
        UniqueConstraint("openai_call_id", name="uq_call_sessions_openai_call_id"),
    )

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
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinic_customers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    openai_call_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
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
        UniqueConstraint(
            "clinic_id",
            "idempotency_key",
            name="uq_appointments_clinic_idempotency",
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
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinic_customers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
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


class AdminRole(StrEnum):
    """Administrative authorization levels."""

    SUPER_ADMIN = "super_admin"
    CLINIC_ADMIN = "clinic_admin"
    OPERATOR = "operator"
    READ_ONLY = "read_only"


class AdminUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Database-backed administrator account."""

    __tablename__ = "admin_users"
    __table_args__ = (UniqueConstraint("username", name="uq_admin_users_username"),)

    username: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        Enum(
            AdminRole,
            name="admin_role",
            native_enum=False,
            create_constraint=True,
            length=32,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=AdminRole.SUPER_ADMIN,
        server_default=AdminRole.SUPER_ADMIN.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), default=0, nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    email: Mapped[str | None] = mapped_column(
        String(320), unique=True, index=True, nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    google_subject: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    auth_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="password"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memberships: Mapped[list[AdminMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AdminMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Clinic-level membership for non-global administrators."""

    __tablename__ = "admin_memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "clinic_id", name="uq_admin_memberships_user_clinic"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[AdminRole] = mapped_column(
        Enum(
            AdminRole,
            name="admin_membership_role",
            native_enum=False,
            create_constraint=True,
            length=32,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=AdminRole.CLINIC_ADMIN,
        server_default=AdminRole.CLINIC_ADMIN.value,
        nullable=False,
    )

    user: Mapped[AdminUser] = relationship(back_populates="memberships")


class AdminSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Revocable server-side browser session."""

    __tablename__ = "admin_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
        Index("ix_admin_sessions_expiry", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped[AdminUser] = relationship(back_populates="sessions")


class OAuthLoginState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use Google OpenID Connect authorization transaction."""

    __tablename__ = "oauth_login_states"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_oauth_login_states_state_hash"),
        Index("ix_oauth_login_states_expiry", "expires_at"),
    )

    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(256), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    portal: Mapped[str] = mapped_column(String(24), nullable=False)
    return_to: Mapped[str] = mapped_column(
        String(1000), nullable=False, server_default="/"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AdminAuditLog(UUIDPrimaryKeyMixin, Base):
    """Immutable audit trail for administrative actions."""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        Index("ix_admin_audit_created", "created_at"),
        Index("ix_admin_audit_user", "user_id", "created_at"),
        Index("ix_admin_audit_clinic", "clinic_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default=text("'{}'"), default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ClinicCustomer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A final customer belonging to exactly one clinic tenant."""

    __tablename__ = "clinic_customers"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "normalized_phone", name="uq_clinic_customers_phone"
        ),
        Index("ix_clinic_customers_clinic_name", "clinic_id", "name"),
        Index("ix_clinic_customers_clinic_active", "clinic_id", "is_active"),
        Index(
            "ix_clinic_customers_clinic_last_contact", "clinic_id", "last_contact_at"
        ),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    display_phone: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_values_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default=text("'{}'"), default=dict, nullable=False
    )
    preferred_worker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"), nullable=True
    )
    personalization_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    first_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    anonymized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ClinicCustomerFieldDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Clinic-controlled schema for customer custom values."""

    __tablename__ = "clinic_customer_field_definitions"
    __table_args__ = (
        UniqueConstraint("clinic_id", "key", name="uq_customer_fields_clinic_key"),
        CheckConstraint(
            "field_type IN ('text','textarea','number','boolean','date','select')",
            name="valid_customer_field_type",
        ),
        Index("ix_customer_fields_clinic_sort", "clinic_id", "sort_order"),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    options_json: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'"), default=list, nullable=False
    )
    required: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), default=0, nullable=False
    )


class ClinicResource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A limited clinic asset required by one or more services."""

    __tablename__ = "clinic_resources"
    __table_args__ = (
        UniqueConstraint("clinic_id", "name", name="uq_clinic_resources_name"),
        CheckConstraint("capacity > 0", name="positive_resource_capacity"),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str] = mapped_column(
        String(48), server_default=text("'other'"), default="other", nullable=False
    )
    capacity: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )
    schedule_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default=text("'{}'"), default=dict, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )


class ServiceResourceRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Quantity of a resource needed by a service."""

    __tablename__ = "service_resource_requirements"
    __table_args__ = (
        UniqueConstraint(
            "service_id", "resource_id", name="uq_service_resource_requirement"
        ),
        CheckConstraint("quantity > 0", name="positive_resource_requirement_quantity"),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinic_resources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )


class ResourceReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Capacity reservation tied to an appointment."""

    __tablename__ = "resource_reservations"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id", "resource_id", name="uq_appointment_resource_reservation"
        ),
        CheckConstraint("quantity > 0", name="positive_reserved_resource_quantity"),
        Index("ix_resource_reservations_window", "resource_id", "start_at", "end_at"),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinic_resources.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CallAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured, non-sensitive post-call analytics."""

    __tablename__ = "call_analyses"
    __table_args__ = (
        UniqueConstraint("call_session_id", name="uq_call_analysis_call"),
        CheckConstraint(
            "sentiment_score BETWEEN -1 AND 1", name="valid_sentiment_score"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="valid_analysis_confidence"),
        CheckConstraint(
            "sentiment_label IN ('positive','neutral','negative','mixed','unknown')",
            name="valid_sentiment_label",
        ),
    )

    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sentiment_label: Mapped[str] = mapped_column(
        String(16), server_default=text("'unknown'"), default="unknown", nullable=False
    )
    sentiment_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), server_default=text("0"), default=Decimal("0"), nullable=False
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), server_default=text("0"), default=Decimal("0"), nullable=False
    )
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolution_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    urgency: Mapped[str] = mapped_column(
        String(24), server_default=text("'normal'"), default="normal", nullable=False
    )
    topics_json: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'"), default=list, nullable=False
    )
    friction_points_json: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'"), default=list, nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    analysis_version: Mapped[str] = mapped_column(
        String(32), server_default=text("'v1'"), default="v1", nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Commercial account paying for one or more clinics."""

    __tablename__ = "billing_accounts"
    __table_args__ = (Index("ix_billing_accounts_status", "status"),)

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    billing_address_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default=text("'{}'"), default=dict, nullable=False
    )
    billing_email: Mapped[str] = mapped_column(String(320), nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), server_default=text("'free'"), default="free", nullable=False
    )


class BillingAccountMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_account_members"
    __table_args__ = (
        UniqueConstraint(
            "billing_account_id", "user_id", name="uq_billing_account_member"
        ),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(24), server_default=text("'member'"), default="member", nullable=False
    )


class BillingProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_products"
    __table_args__ = (UniqueConstraint("code", name="uq_billing_products_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ownership_type: Mapped[str] = mapped_column(
        String(32), server_default=text("'service'"), default="service", nullable=False
    )
    entitlement_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quantity_configurable: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    stripe_product_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )


class BillingPrice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_prices"
    __table_args__ = (
        UniqueConstraint("code", name="uq_billing_prices_code"),
        CheckConstraint("unit_amount_minor >= 0", name="nonnegative_billing_price"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), server_default=text("'EUR'"), default="EUR", nullable=False
    )
    unit_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_type: Mapped[str] = mapped_column(String(24), nullable=False)
    interval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stripe_price_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("ix_purchase_orders_account_created", "billing_account_id", "created_at"),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinics.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), server_default=text("'draft'"), default="draft", nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), server_default=text("'EUR'"), default="EUR", nullable=False
    )
    total_one_time_minor: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), default=0, nullable=False
    )
    total_recurring_minor: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), default=0, nullable=False
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PurchaseOrderItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_order_item_quantity"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_products.id", ondelete="RESTRICT"), nullable=False
    )
    price_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_prices.id", ondelete="RESTRICT"), nullable=False
    )
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_type: Mapped[str] = mapped_column(String(24), nullable=False)
    stripe_price_id_snapshot: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )


class PaymentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_records"
    __table_args__ = (
        Index("ix_payment_records_account_created", "billing_account_id", "created_at"),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinics.id", ondelete="SET NULL"), index=True, nullable=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ClinicSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clinic_subscriptions"
    __table_args__ = (
        Index("ix_clinic_subscriptions_account_status", "billing_account_id", "status"),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_products.id", ondelete="SET NULL"), nullable=True
    )
    price_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_prices.id", ondelete="SET NULL"), nullable=True
    )
    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    stripe_subscription_item_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    quantity: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False, nullable=False
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PhoneProvisioningOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "phone_provisioning_orders"
    __table_args__ = (
        Index("ix_phone_provisioning_status_created", "status", "created_at"),
    )

    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinics.id", ondelete="SET NULL"), index=True, nullable=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinic_subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(48),
        server_default=text("'paid_pending_provisioning'"),
        default="paid_pending_provisioning",
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )
    assigned_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(48), nullable=True)
    external_provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sip_target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ClinicEntitlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clinic_entitlements"
    __table_args__ = (
        UniqueConstraint("clinic_id", "code", name="uq_clinic_entitlement_code"),
    )

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    billing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinic_subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default=text("'{}'"), default=dict, nullable=False
    )


class AuthActionToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Hashed one-use token for email verification and password reset."""

    __tablename__ = "auth_action_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_action_token_hash"),
        Index("ix_auth_action_tokens_user_kind", "user_id", "kind", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WebhookReceipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable idempotency record for externally delivered webhooks."""

    __tablename__ = "webhook_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
        Index("ix_webhook_receipts_status_created", "status", "created_at"),
    )

    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), server_default="processing", default="processing", nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntegrationOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable retry queue for cross-system compensation and reconciliation."""

    __tablename__ = "integration_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_integration_outbox_dedupe"),
        Index("ix_integration_outbox_pending", "status", "next_attempt_at"),
    )

    kind: Mapped[str] = mapped_column(String(120), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(240), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default=text("'{}'"), default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), server_default="pending", default="pending", nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), default=0, nullable=False
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
