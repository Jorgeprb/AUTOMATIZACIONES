"""Pydantic schemas for the multi-clinic administration API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.call_audio import (
    normalize_call_audio_mode,
    requires_external_voice_legal_confirmation,
)
from app.conversation_flows import validate_flow_json
from app.models import (
    AppointmentSource,
    AppointmentStatus,
    CallOutcome,
    CallStatus,
    KnowledgeCategory,
    PhoneProvider,
)

T = TypeVar("T")

CallAudioMode = Literal["openai_hosted_sip", "vps_media_bridge"]
VoiceProvider = Literal[
    "openai",
    "azure",
    "google",
    "elevenlabs",
    "amazon_polly",
    "deepgram",
    "cartesia",
    "resemble",
    "readspeaker",
    "acapela",
    "cereproc",
    "local_coqui",
    "local_chatterbox",
    "custom_http",
]
TelephonyCodec = Literal["pcmu", "pcma", "pcm16"]
OutputAudioFormat = Literal["pcm16", "wav", "mp3", "opus"]


class Page(BaseModel, Generic[T]):
    """Simple offset-page response used by all admin list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class ORMReadModel(BaseModel):
    """Base response model backed by SQLAlchemy attributes."""

    model_config = ConfigDict(from_attributes=True)


class ClinicBase(BaseModel):
    """Shared editable clinic fields."""

    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    timezone: str = Field(default="Europe/Madrid", max_length=64)
    default_language: str = Field(default="es", min_length=2, max_length=16)
    main_phone_number: str = Field(min_length=3, max_length=32)
    address: str | None = None
    website: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    description: str | None = None
    opening_hours_json: dict[str, Any] = Field(default_factory=dict)
    emergency_message: str | None = None
    data_retention_days: int = Field(default=30, ge=1, le=3650)
    is_active: bool = True

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require a valid IANA timezone."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class ClinicCreate(ClinicBase):
    """Create one clinic."""


class ClinicUpdate(BaseModel):
    """Partially update one clinic."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    timezone: str | None = Field(default=None, max_length=64)
    default_language: str | None = Field(default=None, min_length=2, max_length=16)
    main_phone_number: str | None = Field(default=None, min_length=3, max_length=32)
    address: str | None = None
    website: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    description: str | None = None
    opening_hours_json: dict[str, Any] | None = None
    emergency_message: str | None = None
    data_retention_days: int | None = Field(default=None, ge=1, le=3650)
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        """Require a valid IANA timezone when supplied."""
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class ClinicRead(ClinicBase, ORMReadModel):
    """Administrative clinic representation."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PhoneNumberBase(BaseModel):
    """Shared telephone-number fields."""

    provider: PhoneProvider = PhoneProvider.OTHER
    phone_number: str = Field(min_length=3, max_length=32)
    label: str = Field(min_length=1, max_length=120)
    sip_target: str | None = Field(default=None, max_length=500)
    webhook_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    notes: str | None = None


class PhoneNumberCreate(PhoneNumberBase):
    """Create one clinic phone number."""


class PhoneNumberUpdate(BaseModel):
    """Partially update a clinic phone number."""

    provider: PhoneProvider | None = None
    phone_number: str | None = Field(default=None, min_length=3, max_length=32)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    sip_target: str | None = Field(default=None, max_length=500)
    webhook_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    notes: str | None = None


class PhoneNumberRead(PhoneNumberBase, ORMReadModel):
    """Administrative phone-number representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WorkerBase(BaseModel):
    """Shared worker fields."""

    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=120)
    public_description: str | None = None
    calendar_id: str | None = Field(default=None, max_length=320)
    color_id: str | None = Field(default=None, max_length=32)
    phone_extension: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    is_active: bool = True
    working_hours_json: dict[str, Any] = Field(default_factory=dict)


class WorkerCreate(WorkerBase):
    """Create one worker."""


class WorkerUpdate(BaseModel):
    """Partially update one worker."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    public_description: str | None = None
    calendar_id: str | None = Field(default=None, max_length=320)
    color_id: str | None = Field(default=None, max_length=32)
    phone_extension: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    is_active: bool | None = None
    working_hours_json: dict[str, Any] | None = None


class WorkerRead(WorkerBase, ORMReadModel):
    """Administrative worker representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ServiceBase(BaseModel):
    """Shared service and price fields."""

    name: str = Field(min_length=1, max_length=200)
    public_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price_text: str | None = Field(default=None, max_length=200)
    price_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    duration_minutes: int = Field(gt=0)
    buffer_before_minutes: int = Field(default=0, ge=0)
    buffer_after_minutes: int = Field(default=0, ge=0)
    requires_worker: bool = True
    allowed_worker_ids: list[uuid.UUID] | None = None
    is_bookable_by_bot: bool = True
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        """Store ISO-style currency codes in uppercase."""
        return value.upper()


class ServiceCreate(ServiceBase):
    """Create one service."""


class ServiceUpdate(BaseModel):
    """Partially update one service."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    public_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price_text: str | None = Field(default=None, max_length=200)
    price_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    duration_minutes: int | None = Field(default=None, gt=0)
    buffer_before_minutes: int | None = Field(default=None, ge=0)
    buffer_after_minutes: int | None = Field(default=None, ge=0)
    requires_worker: bool | None = None
    allowed_worker_ids: list[uuid.UUID] | None = None
    is_bookable_by_bot: bool | None = None
    is_active: bool | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        """Store ISO-style currency codes in uppercase."""
        return value.upper() if value is not None else None


class ServiceRead(ServiceBase, ORMReadModel):
    """Administrative service representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("allowed_worker_ids", mode="before")
    @classmethod
    def parse_worker_ids(cls, value: object) -> object:
        """Convert JSON string UUIDs to UUID values."""
        return value


class AssistantConfigBase(BaseModel):
    """Shared assistant model, voice, and prompt configuration."""

    name: str = Field(min_length=1, max_length=200)
    realtime_model: str = Field(min_length=1, max_length=120)
    realtime_voice: str = Field(min_length=1, max_length=80)
    call_audio_mode: CallAudioMode = "openai_hosted_sip"
    voice_provider: VoiceProvider = "openai"
    tts_model: str | None = Field(default=None, max_length=160)
    voice_id: str | None = Field(default=None, max_length=240)
    voice_locale: str | None = Field(default=None, max_length=32)
    voice_gender: str | None = Field(default=None, max_length=32)
    voice_speed: Decimal = Field(
        default=Decimal("1.00"),
        ge=Decimal("0.25"),
        le=Decimal("4.00"),
    )
    voice_pitch: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("-24.00"),
        le=Decimal("24.00"),
    )
    voice_stability: Decimal | None = Field(default=None, ge=0, le=1)
    voice_similarity: Decimal | None = Field(default=None, ge=0, le=1)
    voice_temperature: Decimal | None = Field(default=None, ge=0, le=2)
    output_audio_format: OutputAudioFormat = "pcm16"
    telephony_codec: TelephonyCodec = "pcmu"
    external_voice_legal_confirmed: bool = False
    voice_instructions: str | None = None
    voice_preset: str | None = Field(default=None, max_length=80)
    tts_preview_voice: str | None = Field(default=None, max_length=240)
    fallback_voice: str | None = Field(default=None, max_length=240)
    speech_speed: Literal["slow", "normal", "fast"] = "normal"
    pause_style: Literal["short", "natural", "slow"] = "natural"
    phone_reading_style: Literal["digits", "groups", "natural"] = "groups"
    date_reading_style: Literal["natural", "numeric"] = "natural"
    price_reading_style: Literal["brief", "clear", "detailed"] = "clear"
    allow_interruptions: bool = True
    idle_timeout_ms: int | None = Field(default=None, ge=1000, le=60000)
    ai_disclosure_enabled: bool = True
    ai_disclosure_message: str | None = None
    preview_audio_format: Literal["mp3", "wav", "opus"] = "mp3"
    language: str = Field(default="es", min_length=2, max_length=16)
    temperature: Decimal | None = Field(default=None, ge=0, le=2)
    first_message: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1, max_length=12000)
    safety_prompt: str = Field(min_length=1)
    booking_policy_prompt: str = Field(min_length=1)
    cancellation_policy_prompt: str = Field(min_length=1)
    transfer_policy_prompt: str = Field(min_length=1)
    tone: Literal["profesional", "cercano", "comercial", "breve", "formal"] = (
        "profesional"
    )
    response_length: Literal["corta", "normal", "detallada"] = "normal"
    ask_patient_name: bool = True
    ask_patient_phone: bool = True
    ask_general_reason: bool = True
    allow_booking_without_worker: bool = True
    allow_bookings: bool = True
    allow_price_answers: bool = True
    ask_service: bool = True
    max_proposed_slots: int = Field(default=3, ge=1, le=10)
    max_consecutive_questions: int = Field(default=2, ge=1, le=5)
    conversation_style: Literal["natural", "formal", "comercial", "breve"] = "natural"
    initiative_level: Literal["bajo", "medio", "alto"] = "medio"
    commercial_call_handling: Literal[
        "declinar", "transferir", "responder_basico"
    ] = "declinar"
    allow_cancellations: bool = True
    allow_reschedules: bool = True
    natural_confirmation_required: bool = True
    avoid_exact_confirmation_phrases: bool = True
    additional_instructions: str | None = None
    forbidden_phrases: str | None = None
    no_availability_message: str | None = None
    missing_calendar_message: str | None = None
    emergency_message: str | None = None
    human_transfer_message: str | None = None
    human_transfer_rules: str | None = None
    commercial_call_message: str | None = None
    conversation_extra_rules: str | None = None
    closing_message: str | None = None
    use_prices: bool = True
    use_knowledge_base: bool = True
    strict_calendar_mode: bool = True
    transcript_enabled: bool = False
    recording_enabled: bool = False
    conversation_retention_days: int = Field(default=30, ge=1, le=3650)
    conversation_flow_id: uuid.UUID | None = None
    is_active: bool = False

    @model_validator(mode="after")
    def validate_dual_call_audio_policy(self) -> AssistantConfigBase:
        """Keep OpenAI hosted SIP compatible and bridge external voices."""
        self.call_audio_mode = cast(
            CallAudioMode,
            normalize_call_audio_mode(
                voice_provider=self.voice_provider,
                requested_mode=self.call_audio_mode,
            ),
        )
        if (
            requires_external_voice_legal_confirmation(self.voice_provider)
            and not self.external_voice_legal_confirmed
        ):
            raise ValueError(
                "external_voice_legal_confirmed must be true for cloned or "
                "custom external voice providers."
            )
        return self


class AssistantConfigCreate(AssistantConfigBase):
    """Create one assistant configuration."""


class AssistantConfigUpdate(BaseModel):
    """Partially update one assistant configuration."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    realtime_model: str | None = Field(default=None, min_length=1, max_length=120)
    realtime_voice: str | None = Field(default=None, min_length=1, max_length=80)
    call_audio_mode: CallAudioMode | None = None
    voice_provider: VoiceProvider | None = None
    tts_model: str | None = Field(default=None, max_length=160)
    voice_id: str | None = Field(default=None, max_length=240)
    voice_locale: str | None = Field(default=None, max_length=32)
    voice_gender: str | None = Field(default=None, max_length=32)
    voice_speed: Decimal | None = Field(
        default=None,
        ge=Decimal("0.25"),
        le=Decimal("4.00"),
    )
    voice_pitch: Decimal | None = Field(
        default=None,
        ge=Decimal("-24.00"),
        le=Decimal("24.00"),
    )
    voice_stability: Decimal | None = Field(default=None, ge=0, le=1)
    voice_similarity: Decimal | None = Field(default=None, ge=0, le=1)
    voice_temperature: Decimal | None = Field(default=None, ge=0, le=2)
    output_audio_format: OutputAudioFormat | None = None
    telephony_codec: TelephonyCodec | None = None
    external_voice_legal_confirmed: bool | None = None
    voice_instructions: str | None = None
    voice_preset: str | None = Field(default=None, max_length=80)
    tts_preview_voice: str | None = Field(default=None, max_length=240)
    fallback_voice: str | None = Field(default=None, max_length=240)
    speech_speed: Literal["slow", "normal", "fast"] | None = None
    pause_style: Literal["short", "natural", "slow"] | None = None
    phone_reading_style: Literal["digits", "groups", "natural"] | None = None
    date_reading_style: Literal["natural", "numeric"] | None = None
    price_reading_style: Literal["brief", "clear", "detailed"] | None = None
    allow_interruptions: bool | None = None
    idle_timeout_ms: int | None = Field(default=None, ge=1000, le=60000)
    ai_disclosure_enabled: bool | None = None
    ai_disclosure_message: str | None = None
    preview_audio_format: Literal["mp3", "wav", "opus"] | None = None
    language: str | None = Field(default=None, min_length=2, max_length=16)
    temperature: Decimal | None = Field(default=None, ge=0, le=2)
    first_message: str | None = Field(default=None, min_length=1)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=12000)
    safety_prompt: str | None = Field(default=None, min_length=1)
    booking_policy_prompt: str | None = Field(default=None, min_length=1)
    cancellation_policy_prompt: str | None = Field(default=None, min_length=1)
    transfer_policy_prompt: str | None = Field(default=None, min_length=1)
    tone: (
        Literal["profesional", "cercano", "comercial", "breve", "formal"] | None
    ) = None
    response_length: Literal["corta", "normal", "detallada"] | None = None
    ask_patient_name: bool | None = None
    ask_patient_phone: bool | None = None
    ask_general_reason: bool | None = None
    allow_booking_without_worker: bool | None = None
    allow_bookings: bool | None = None
    allow_price_answers: bool | None = None
    ask_service: bool | None = None
    max_proposed_slots: int | None = Field(default=None, ge=1, le=10)
    max_consecutive_questions: int | None = Field(default=None, ge=1, le=5)
    conversation_style: (
        Literal["natural", "formal", "comercial", "breve"] | None
    ) = None
    initiative_level: Literal["bajo", "medio", "alto"] | None = None
    commercial_call_handling: (
        Literal["declinar", "transferir", "responder_basico"] | None
    ) = None
    allow_cancellations: bool | None = None
    allow_reschedules: bool | None = None
    natural_confirmation_required: bool | None = None
    avoid_exact_confirmation_phrases: bool | None = None
    additional_instructions: str | None = None
    forbidden_phrases: str | None = None
    no_availability_message: str | None = None
    missing_calendar_message: str | None = None
    emergency_message: str | None = None
    human_transfer_message: str | None = None
    human_transfer_rules: str | None = None
    commercial_call_message: str | None = None
    conversation_extra_rules: str | None = None
    closing_message: str | None = None
    use_prices: bool | None = None
    use_knowledge_base: bool | None = None
    strict_calendar_mode: bool | None = None
    transcript_enabled: bool | None = None
    recording_enabled: bool | None = None
    conversation_retention_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
    )
    conversation_flow_id: uuid.UUID | None = None
    is_active: bool | None = None


class AssistantConfigRead(AssistantConfigBase, ORMReadModel):
    """Administrative assistant configuration representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AssistantVoicePreviewRequest(BaseModel):
    """One-off voice preview request for the assistant editor."""

    text: str = Field(min_length=1, max_length=2000)
    realtime_voice: str = Field(min_length=1, max_length=80)
    realtime_model: str | None = Field(default=None, max_length=120)
    call_audio_mode: CallAudioMode = "openai_hosted_sip"
    voice_provider: VoiceProvider = "openai"
    tts_model: str | None = Field(default=None, max_length=160)
    voice_id: str | None = Field(default=None, max_length=240)
    voice_locale: str | None = Field(default=None, max_length=32)
    voice_gender: str | None = Field(default=None, max_length=32)
    voice_speed: Decimal = Field(
        default=Decimal("1.00"),
        ge=Decimal("0.25"),
        le=Decimal("4.00"),
    )
    voice_pitch: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("-24.00"),
        le=Decimal("24.00"),
    )
    voice_stability: Decimal | None = Field(default=None, ge=0, le=1)
    voice_similarity: Decimal | None = Field(default=None, ge=0, le=1)
    voice_temperature: Decimal | None = Field(default=None, ge=0, le=2)
    output_audio_format: OutputAudioFormat = "pcm16"
    telephony_codec: TelephonyCodec = "pcmu"
    external_voice_legal_confirmed: bool = False
    tts_preview_voice: str | None = Field(default=None, max_length=240)
    fallback_voice: str | None = Field(default=None, max_length=240)
    voice_preset: str | None = Field(default=None, max_length=80)
    voice_instructions: str | None = None
    speech_speed: Literal["slow", "normal", "fast"] = "normal"
    pause_style: Literal["short", "natural", "slow"] = "natural"
    phone_reading_style: Literal["digits", "groups", "natural"] = "groups"
    date_reading_style: Literal["natural", "numeric"] = "natural"
    price_reading_style: Literal["brief", "clear", "detailed"] = "clear"
    allow_interruptions: bool = True
    idle_timeout_ms: int | None = Field(default=None, ge=1000, le=60000)
    ai_disclosure_enabled: bool = True
    ai_disclosure_message: str | None = None
    preview_audio_format: Literal["mp3", "wav", "opus"] = "mp3"


class RealtimePreviewSessionCreate(BaseModel):
    """Create one browser WebRTC Realtime preview with unsaved config values."""

    assistant_config_id: uuid.UUID | None = None
    config: AssistantConfigCreate


class RealtimePreviewSessionResponse(BaseModel):
    """Ephemeral browser credentials for one Realtime preview session."""

    id: uuid.UUID
    call_session_id: uuid.UUID
    client_secret: str
    model: str
    voice: str
    call_audio_mode: CallAudioMode
    voice_provider: VoiceProvider
    external_tts_required: bool = False
    initial_message: str
    expires_at: datetime


class RealtimePreviewToolCallRequest(BaseModel):
    """Tool call emitted by the browser Realtime data channel."""

    name: str = Field(min_length=1, max_length=120)
    call_id: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict)


class RealtimePreviewToolCallResponse(BaseModel):
    """Tool output ready to send back to the Realtime data channel."""

    call_id: str
    output: dict[str, Any]


class RealtimePreviewHeartbeatResponse(BaseModel):
    """Heartbeat acknowledgement for a live preview session."""

    ok: bool
    expires_at: datetime


class PromptPreviewResponse(BaseModel):
    """Rendered tenant prompt and effective Realtime configuration."""

    clinic_id: uuid.UUID
    config_id: uuid.UUID
    realtime_model: str
    realtime_voice: str
    language: str
    first_message: str
    prompt: str


class AssistantOptionRead(BaseModel):
    """One locally allowed Realtime option."""

    id: str
    label: str
    recommended: bool = False


class VoiceProviderRead(BaseModel):
    """Safe voice provider metadata for the admin UI."""

    id: str
    display_name: str
    configured: bool
    supports_tts: bool = True
    supports_streaming: bool = False
    supports_telephony_codec: bool = False
    supports_stt: bool = False
    supports_voice_clone: bool = False
    requires_consent: bool = False
    recommended: bool = False
    enabled: bool = True
    notes: str | None = None


class VoiceCatalogRead(ORMReadModel):
    """One selectable voice in the synchronized catalog."""

    id: uuid.UUID
    provider: str
    model: str
    voice_id: str
    display_name: str
    locale: str | None = None
    language: str | None = None
    gender: str | None = None
    supports_streaming: bool
    supports_telephony_codec: bool
    supports_voice_clone: bool
    requires_consent: bool
    recommended: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


class VoiceProviderSyncResponse(BaseModel):
    """Result of syncing static/remote voice catalogs."""

    ok: bool
    synced: dict[str, int]


class AssistantOptionsResponse(BaseModel):
    """Models, voices and provider capabilities configurable from UI."""

    default_model: str
    default_voice: str
    models: list[AssistantOptionRead]
    voices: list[AssistantOptionRead]
    languages: list[AssistantOptionRead]
    voice_providers: list[VoiceProviderRead] = Field(default_factory=list)
    output_audio_formats: list[str] = Field(default_factory=list)
    telephony_codecs: list[str] = Field(default_factory=list)


class AssistantRecommendedTemplateResponse(BaseModel):
    """Recommended editable assistant prompt defaults for new clinics."""

    first_message: str
    system_prompt: str
    safety_prompt: str
    booking_policy_prompt: str
    cancellation_policy_prompt: str
    transfer_policy_prompt: str
    voice_instructions: str | None = None
    voice_preset: str | None = None
    tts_preview_voice: str | None = None
    fallback_voice: str | None = None
    speech_speed: Literal["slow", "normal", "fast"] = "normal"
    pause_style: Literal["short", "natural", "slow"] = "natural"
    phone_reading_style: Literal["digits", "groups", "natural"] = "groups"
    date_reading_style: Literal["natural", "numeric"] = "natural"
    price_reading_style: Literal["brief", "clear", "detailed"] = "clear"
    allow_interruptions: bool = True
    idle_timeout_ms: int | None = Field(default=None, ge=1000, le=60000)
    ai_disclosure_enabled: bool = True
    ai_disclosure_message: str | None = None
    preview_audio_format: Literal["mp3", "wav", "opus"] = "mp3"
    tone: Literal["profesional", "cercano", "comercial", "breve", "formal"]
    response_length: Literal["corta", "normal", "detallada"]
    ask_patient_name: bool
    ask_patient_phone: bool
    ask_general_reason: bool
    allow_booking_without_worker: bool
    allow_bookings: bool
    allow_price_answers: bool
    ask_service: bool
    max_proposed_slots: int = Field(ge=1, le=10)
    max_consecutive_questions: int = Field(ge=1, le=5)
    conversation_style: Literal["natural", "formal", "comercial", "breve"]
    initiative_level: Literal["bajo", "medio", "alto"]
    commercial_call_handling: Literal[
        "declinar", "transferir", "responder_basico"
    ]
    allow_cancellations: bool
    allow_reschedules: bool
    natural_confirmation_required: bool
    avoid_exact_confirmation_phrases: bool
    additional_instructions: str
    forbidden_phrases: str
    no_availability_message: str
    missing_calendar_message: str
    emergency_message: str
    human_transfer_message: str
    human_transfer_rules: str
    commercial_call_message: str
    conversation_extra_rules: str
    closing_message: str
    use_prices: bool
    use_knowledge_base: bool
    strict_calendar_mode: bool


class PromptContextServiceRead(BaseModel):
    """One active service as exposed to the LLM context."""

    id: uuid.UUID
    public_name: str
    description: str | None
    price: str
    duration_minutes: int
    total_duration_minutes: int
    requires_worker: bool
    worker_names: list[str]
    is_bookable_by_bot: bool


class PromptContextWorkerRead(BaseModel):
    """One active worker as exposed to the LLM context."""

    id: uuid.UUID
    name: str
    role: str
    calendar_linked: bool


class PromptContextKnowledgeRead(BaseModel):
    """One active knowledge item as exposed to the LLM context."""

    id: uuid.UUID
    title: str
    category: KnowledgeCategory
    content: str
    priority: int


class PromptContextPreviewResponse(BaseModel):
    """Structured, secret-free preview of effective active LLM context."""

    clinic_id: uuid.UUID
    assistant_config_id: uuid.UUID | None
    services: list[PromptContextServiceRead]
    workers: list[PromptContextWorkerRead]
    knowledge_items: list[PromptContextKnowledgeRead]
    warnings: list[str]


class KnowledgeItemBase(BaseModel):
    """Shared knowledge-base item fields."""

    title: str = Field(min_length=1, max_length=240)
    category: KnowledgeCategory
    content: str = Field(min_length=1)
    source_type: Literal["manual", "pdf", "url"] = "manual"
    source: str | None = Field(default=None, max_length=1000)
    imported_at: datetime | None = None
    import_status: str = Field(default="manual", max_length=32)
    is_active: bool = True
    priority: int = 0


class KnowledgeItemCreate(KnowledgeItemBase):
    """Create one knowledge item."""


class KnowledgeItemUpdate(BaseModel):
    """Partially update one knowledge item."""

    title: str | None = Field(default=None, min_length=1, max_length=240)
    category: KnowledgeCategory | None = None
    content: str | None = Field(default=None, min_length=1)
    source_type: Literal["manual", "pdf", "url"] | None = None
    source: str | None = Field(default=None, max_length=1000)
    imported_at: datetime | None = None
    import_status: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    priority: int | None = None


class KnowledgeItemRead(KnowledgeItemBase, ORMReadModel):
    """Administrative knowledge item representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class KnowledgeImportPreviewResponse(BaseModel):
    """Extracted knowledge ready to preview before saving."""

    title: str
    category: KnowledgeCategory
    content: str
    source_type: Literal["pdf", "url"]
    source: str
    imported_at: datetime
    import_status: str
    character_count: int


class KnowledgeUrlImportRequest(BaseModel):
    """URL import request with editable metadata."""

    url: str = Field(min_length=8, max_length=1000)
    title: str | None = Field(default=None, max_length=240)
    category: KnowledgeCategory = KnowledgeCategory.FAQ
    priority: int = 0
    is_active: bool = True


class ConversationFlowBase(BaseModel):
    """Shared structured-flow fields."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    flow_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("flow_json")
    @classmethod
    def validate_definition(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Require the supported maintainable flow JSON contract."""
        return validate_flow_json(value)


class ConversationFlowCreate(ConversationFlowBase):
    """Create one conversation flow."""


class ConversationFlowUpdate(BaseModel):
    """Partially update one conversation flow."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    flow_json: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("flow_json")
    @classmethod
    def validate_definition(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Validate partial flow updates when JSON is supplied."""
        return validate_flow_json(value) if value is not None else None


class ConversationFlowRead(ConversationFlowBase, ORMReadModel):
    """Administrative flow representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ConversationFlowTemplateRead(BaseModel):
    """One built-in flow template ready for the JSON editor."""

    key: str
    name: str
    description: str
    flow_json: dict[str, Any]


class CallEventRead(ORMReadModel):
    """Stored raw conversation event."""

    id: uuid.UUID
    event_type: str
    payload_json: dict[str, Any]
    created_at: datetime


class CallRead(ORMReadModel):
    """Administrative call and conversation representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID | None
    phone_number_id: uuid.UUID | None
    assistant_config_id: uuid.UUID | None
    openai_call_id: str
    provider_call_id: str | None
    caller_phone: str
    caller_name: str | None
    called_number: str
    status: CallStatus
    detected_intent: str | None
    outcome: CallOutcome | None
    recording_enabled: bool
    transcript_enabled: bool
    conversation_state_json: dict[str, Any]
    transcript_text: str | None
    summary_text: str | None
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CallDetail(CallRead):
    """Call representation with raw conversation events."""

    events: list[CallEventRead]


class CallAppointmentRead(BaseModel):
    """Appointment context linked to one call."""

    id: uuid.UUID
    worker_id: uuid.UUID
    worker_name: str
    service_id: uuid.UUID | None
    service_name: str | None
    patient_name: str
    patient_phone: str
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    source: AppointmentSource
    google_event_id: str


class CallAnalysisRead(CallRead):
    """Call list row enriched with duration and booking outcome."""

    duration_seconds: int | None
    appointment_created: bool
    appointment: CallAppointmentRead | None


class CallAnalysisDetail(CallAnalysisRead):
    """Complete call analysis with classified technical events."""

    clinic_name: str
    events: list[CallEventRead]
    tool_calls: list[CallEventRead]
    errors: list[CallEventRead]


class CallDebugResponse(BaseModel):
    """Downloadable troubleshooting payload for one call."""

    call: CallAnalysisDetail
    generated_at: datetime


class CallPrivacyResponse(BaseModel):
    """Result of a destructive or privacy-preserving call action."""

    status: Literal[
        "content_deleted",
        "phone_anonymized",
        "deleted",
        "anonymized",
    ]
    call_session_id: uuid.UUID
    appointment_preserved: bool


class CallCreate(BaseModel):
    """Create or import one administrative call record."""

    phone_number_id: uuid.UUID | None = None
    assistant_config_id: uuid.UUID | None = None
    openai_call_id: str = Field(min_length=1, max_length=128)
    provider_call_id: str | None = Field(default=None, max_length=128)
    caller_phone: str = Field(min_length=1, max_length=32)
    caller_name: str | None = Field(default=None, max_length=200)
    called_number: str = Field(min_length=1, max_length=32)
    status: CallStatus = CallStatus.INCOMING
    detected_intent: str | None = Field(default=None, max_length=160)
    outcome: CallOutcome | None = None
    recording_enabled: bool = False
    transcript_enabled: bool = False
    conversation_state_json: dict[str, Any] = Field(default_factory=dict)
    transcript_text: str | None = None
    summary_text: str | None = None
    started_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: AwareDatetime | None = None


class CallUpdate(BaseModel):
    """Editable administrative call fields."""

    phone_number_id: uuid.UUID | None = None
    assistant_config_id: uuid.UUID | None = None
    provider_call_id: str | None = Field(default=None, max_length=128)
    caller_phone: str | None = Field(default=None, min_length=1, max_length=32)
    caller_name: str | None = Field(default=None, max_length=200)
    called_number: str | None = Field(default=None, min_length=1, max_length=32)
    status: CallStatus | None = None
    detected_intent: str | None = Field(default=None, max_length=160)
    outcome: CallOutcome | None = None
    recording_enabled: bool | None = None
    transcript_enabled: bool | None = None
    transcript_text: str | None = None
    summary_text: str | None = None
    ended_at: AwareDatetime | None = None


class AppointmentCreate(BaseModel):
    """Create a local administrative appointment."""

    worker_id: uuid.UUID
    service_id: uuid.UUID | None = None
    patient_name: str = Field(min_length=1, max_length=200)
    patient_phone: str = Field(min_length=3, max_length=32)
    reason: str | None = Field(default=None, max_length=300)
    start_at: AwareDatetime
    end_at: AwareDatetime
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    call_session_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> AppointmentCreate:
        """Require a positive appointment interval."""
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class AppointmentUpdate(BaseModel):
    """Partially update an administrative appointment."""

    worker_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    patient_name: str | None = Field(default=None, min_length=1, max_length=200)
    patient_phone: str | None = Field(default=None, min_length=3, max_length=32)
    reason: str | None = Field(default=None, max_length=300)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    status: AppointmentStatus | None = None
    call_session_id: uuid.UUID | None = None


class AppointmentRead(ORMReadModel):
    """Administrative appointment representation."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    worker_id: uuid.UUID
    service_id: uuid.UUID | None
    call_session_id: uuid.UUID | None
    google_calendar_id: str
    google_event_id: str
    patient_name: str
    patient_phone: str
    reason: str | None
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    source: AppointmentSource
    created_at: datetime
    updated_at: datetime


class AppointmentAnalysisRead(AppointmentRead):
    """Appointment row enriched with public worker and service names."""

    worker_name: str
    service_name: str | None


class TestSessionCreate(BaseModel):
    """Start one browser-based assistant simulation."""

    assistant_config_id: uuid.UUID
    use_real_calendar: bool = False
    engine: Literal["simulator", "openai"] | None = None


class TestSessionMessageCreate(BaseModel):
    """Send one patient message to a test session."""

    message: str = Field(min_length=1, max_length=4000)


class TestSessionTTSRequest(BaseModel):
    """Text to synthesize for the browser test console."""

    text: str = Field(min_length=1, max_length=4000)


class TestToolTrace(BaseModel):
    """One tool execution exposed in the testing console."""

    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class TestChatMessage(BaseModel):
    """One persisted user or assistant chat message."""

    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    action: str | None = None
    tool_calls: list[TestToolTrace] = Field(default_factory=list)


class TestExtractedState(BaseModel):
    """Human-readable fields extracted by the deterministic simulator."""

    patient_name: str | None = None
    patient_phone: str | None = None
    service_name: str | None = None
    worker_name: str | None = None
    preferred_date: str | None = None
    preferred_time_window: str | None = None
    phase: str = "idle"
    appointment_confirmed: bool = False
    appointment_id: uuid.UUID | None = None
    emergency_detected: bool = False


class TestSessionRead(BaseModel):
    """Complete state required to render the browser test console."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    assistant_config_id: uuid.UUID
    assistant_config_name: str
    use_real_calendar: bool
    engine: Literal["simulator", "openai"]
    prompt: str
    messages: list[TestChatMessage]
    state: TestExtractedState
    tool_calls: list[TestToolTrace]
    warnings: list[str]
    is_closed: bool = False
    created_at: datetime
    updated_at: datetime


class SetupStatusItem(BaseModel):
    """One production-readiness step for a clinic."""

    key: str
    label: str
    completed: bool
    automatic: bool = True
    href: str
    help: str


class SetupStatusResponse(BaseModel):
    """Production-readiness summary for one clinic."""

    clinic_id: uuid.UUID
    completed: bool
    items: list[SetupStatusItem]
    warnings: list[str]
    blocking_errors: list[str]


class DashboardLastCall(BaseModel):
    """Compact representation of the latest real inbound call."""

    id: uuid.UUID
    caller_phone: str
    called_number: str
    status: CallStatus
    outcome: CallOutcome | None
    started_at: datetime


class ClinicDashboardResponse(BaseModel):
    """Operational counters and readiness cards for one clinic."""

    clinic_id: uuid.UUID
    configuration_complete: bool
    google_calendar_connected: bool
    phone_number_configured: bool
    assistant_active: bool
    active_workers: int
    bookable_services: int
    calls_last_24h: int
    upcoming_appointments: int
    recent_errors: int
    last_call: DashboardLastCall | None


class DeleteResponse(BaseModel):
    """Generic successful deletion response."""

    status: str = "deleted"
    id: uuid.UUID
