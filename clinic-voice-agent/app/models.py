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
        CheckConstraint(
            "max_proposed_slots BETWEEN 1 AND 10",
            name="valid_assistant_max_proposed_slots",
        ),
        CheckConstraint(
            (
                "conversation_style IN "
                "('natural', 'formal', 'comercial', 'breve')"
            ),
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
            "voice_speed BETWEEN 0.25 AND 4.00",
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
    allow_interruptions: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
        nullable=False,
    )
    idle_timeout_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    idempotency_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True
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


class AdminRole(StrEnum):
    """Administrative authorization levels."""

    SUPER_ADMIN = "super_admin"
    CLINIC_ADMIN = "clinic_admin"
    OPERATOR = "operator"
    READ_ONLY = "read_only"


class AdminUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Database-backed administrator account."""

    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_admin_users_username"),
    )

    username: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        Enum(
            AdminRole,
            name="admin_role",
            native_enum=False,
            create_constraint=True,
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
