"""Internal voice gateway endpoints used by the VPS SIP media bridge."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audio import TTSGenerationError, synthesize_speech
from app.config import Settings, get_settings
from app.db import get_db, get_session_factory
from app.models import AssistantConfig, CallSession, CallStatus, Clinic
from app.openai_realtime.prompt_builder import (
    ActiveAssistantConfigMissing,
    ClinicContext,
    UnknownCalledNumber,
    build_clinic_context,
    build_realtime_instructions,
    resolve_clinic_by_called_number,
)
from app.openai_realtime.tools import (
    ToolExecutionContext,
    execute_realtime_tool,
    get_realtime_tools,
)
from app.voice_profile import build_voice_instruction_block

router = APIRouter(prefix="/internal/voice", tags=["internal-voice"])


class VoiceContextRequest(BaseModel):
    """Data extracted by SIP gateway before media starts."""

    called_number: str | None = Field(default=None, max_length=128)
    caller_phone: str | None = Field(default=None, max_length=128)
    caller: str | None = Field(default=None, max_length=128)
    callee: str | None = Field(default=None, max_length=128)
    sip_to: str | None = Field(default=None, max_length=512)
    sip_from: str | None = Field(default=None, max_length=512)
    openai_call_id: str = Field(min_length=1, max_length=128)
    provider_call_id: str | None = Field(default=None, max_length=128)


class VoiceClinicInfo(BaseModel):
    """Safe clinic data returned to the internal media bridge."""

    id: uuid.UUID
    name: str
    timezone: str
    default_language: str
    main_phone_number: str
    address: str | None
    website: str | None
    email: str | None
    description: str | None


class VoiceContextResponse(BaseModel):
    """Rendered assistant context consumed by sip-gateway."""

    clinic_id: uuid.UUID
    call_session_id: uuid.UUID
    phone_number_id: uuid.UUID | None
    assistant_config_id: uuid.UUID
    model: str
    realtime_voice: str
    call_audio_mode: str
    voice_provider: str
    tts_model: str | None
    voice_id: str | None
    voice_locale: str | None
    voice_gender: str | None
    azure_speech_region: str | None
    voice_style: str | None
    voice_speed: str
    voice_pitch: str
    voice_stability: str | None
    voice_similarity: str | None
    voice_temperature: str | None
    output_audio_format: str
    telephony_codec: str
    preview_audio_format: str
    allow_interruptions: bool
    idle_timeout_ms: int | None
    transcript_enabled: bool
    language: str
    first_message: str
    instructions: str
    prompt: str
    caller: str | None
    called_number: str
    resolved_called_number: str | None
    clinic: VoiceClinicInfo
    tools: list[dict[str, Any]]


class InternalTTSRequest(BaseModel):
    """Provider-agnostic TTS request from the SIP gateway."""

    clinic_id: uuid.UUID
    text: str = Field(min_length=1, max_length=2000)
    voice_provider: str = "openai"
    realtime_voice: str = "marin"
    tts_model: str | None = None
    voice_id: str | None = None
    voice_locale: str | None = None
    voice_gender: str | None = None
    azure_speech_region: str | None = None
    voice_style: str | None = None
    voice_speed: Decimal = Decimal("1.00")
    voice_pitch: Decimal = Decimal("0.00")
    voice_stability: Decimal | None = None
    voice_similarity: Decimal | None = None
    voice_temperature: Decimal | None = None
    output_audio_format: str = "pcm16"
    telephony_codec: str = "pcmu"
    preview_audio_format: str = "wav"
    call_audio_mode: str = "vps_media_bridge"
    external_voice_legal_confirmed: bool = True
    tts_preview_voice: str | None = None
    fallback_voice: str | None = None
    voice_preset: str | None = None
    voice_instructions: str | None = None
    speech_speed: str = "normal"
    pause_style: str = "natural"
    phone_reading_style: str = "groups"
    date_reading_style: str = "natural"
    price_reading_style: str = "clear"
    allow_interruptions: bool = True
    idle_timeout_ms: int | None = None
    ai_disclosure_enabled: bool = True
    ai_disclosure_message: str | None = None


class InternalToolRequest(BaseModel):
    """Tool execution request from the SIP gateway."""

    clinic_id: uuid.UUID
    call_session_id: uuid.UUID
    openai_call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)


def _decimal_to_str(value: Decimal | None) -> str | None:
    """Render Decimal config values for JSON."""
    return str(value) if value is not None else None


PHONE_RE = re.compile(r"\+?\d[\d\s().-]{3,}\d")
SIP_USER_RE = re.compile(r"sip:([^@;>\s]+)", flags=re.IGNORECASE)


def _normalize_phone_candidates(value: str | None) -> tuple[str, ...]:
    """Return exact-match phone candidates from SIP-ish text without broad scans."""
    if not value:
        return ()
    raw = value.strip()
    values: list[str] = []
    for candidate in [raw, *SIP_USER_RE.findall(raw), *PHONE_RE.findall(raw)]:
        candidate = candidate.strip().strip('"<>')
        digits = "".join(character for character in candidate if character.isdigit())
        if len(digits) < 5:
            continue
        values.append(candidate)
        values.append(digits)
        values.append(f"+{digits}")
    deduplicated: list[str] = []
    for item in values:
        if item and item not in deduplicated:
            deduplicated.append(item[:64])
    return tuple(deduplicated)


def _called_number_candidates(payload: VoiceContextRequest) -> tuple[str, ...]:
    """Build ordered DID candidates from gateway payload."""
    values: list[str] = []
    for item in (payload.called_number, payload.callee, payload.sip_to):
        for candidate in _normalize_phone_candidates(item):
            if candidate not in values:
                values.append(candidate)
    return tuple(values)


def _caller_phone(payload: VoiceContextRequest) -> str:
    """Pick the safest caller value for the call session."""
    for item in (payload.caller_phone, payload.caller, payload.sip_from):
        candidates = _normalize_phone_candidates(item)
        if candidates:
            return candidates[0][:32]
        if item and item.strip():
            return item.strip()[:32]
    return "unknown"


def _single_active_clinic_fallback(session: Session) -> ClinicContext:
    """Resolve only when fallback cannot cross tenant boundaries."""
    clinic_ids = list(
        session.scalars(
            select(Clinic.id)
            .join(AssistantConfig, AssistantConfig.clinic_id == Clinic.id)
            .where(
                Clinic.is_active.is_(True),
                AssistantConfig.is_active.is_(True),
            )
            .order_by(Clinic.created_at, Clinic.id)
        ).unique()
    )
    if len(clinic_ids) == 1:
        return build_clinic_context(session, clinic_id=clinic_ids[0])
    if not clinic_ids:
        raise ActiveAssistantConfigMissing(
            "No active clinic with an active assistant configuration is available."
        )
    raise UnknownCalledNumber(
        "No active clinic matches the called number and fallback is unsafe because "
        "multiple active clinics have active assistant configurations."
    )


def _resolve_context_from_payload(
    payload: VoiceContextRequest,
    session: Session,
) -> tuple[ClinicContext, str | None]:
    """Resolve tenant context from called DID candidates or safe fallback."""
    candidates = _called_number_candidates(payload)
    last_config_error: ActiveAssistantConfigMissing | None = None
    for candidate in candidates:
        try:
            context = resolve_clinic_by_called_number(candidate, session=session)
            return context, candidate
        except UnknownCalledNumber:
            continue
        except ActiveAssistantConfigMissing as exc:
            last_config_error = exc
    if last_config_error is not None:
        raise last_config_error
    if not candidates:
        return _single_active_clinic_fallback(session), None
    raise UnknownCalledNumber("No active clinic matches the called number candidates.")


def _clinic_info(clinic: Clinic) -> VoiceClinicInfo:
    """Serialize non-secret clinic basics for the gateway."""
    return VoiceClinicInfo(
        id=clinic.id,
        name=clinic.name,
        timezone=clinic.timezone,
        default_language=clinic.default_language,
        main_phone_number=clinic.main_phone_number,
        address=clinic.address,
        website=clinic.website,
        email=clinic.email,
        description=clinic.description,
    )


@router.post("/context", response_model=VoiceContextResponse)
def create_voice_context(
    payload: VoiceContextRequest,
    session: Annotated[Session, Depends(get_db)],
) -> VoiceContextResponse:
    """Resolve DID to clinic context and create a CallSession for tools."""
    try:
        context, resolved_candidate = _resolve_context_from_payload(payload, session)
    except UnknownCalledNumber as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "clinic_not_found",
                "message": str(exc),
                "called_number_candidates": list(_called_number_candidates(payload)),
                "callee": payload.callee,
            },
        ) from exc
    except ActiveAssistantConfigMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "assistant_config_missing", "message": str(exc)},
        ) from exc

    config = context.active_assistant_config
    caller_phone = _caller_phone(payload)
    called_number = (
        context.phone_number.phone_number
        if context.phone_number is not None
        else resolved_candidate
        or payload.called_number
        or payload.callee
        or "unknown"
    )[:32]
    call_session = CallSession(
        clinic_id=context.clinic.id,
        phone_number_id=context.phone_number.id if context.phone_number else None,
        assistant_config_id=config.id,
        openai_call_id=payload.openai_call_id,
        provider_call_id=payload.provider_call_id,
        caller_phone=caller_phone,
        called_number=called_number,
        status=CallStatus.ACTIVE,
        recording_enabled=config.recording_enabled,
        transcript_enabled=config.transcript_enabled,
        conversation_state_json={
            "source": "vps_media_bridge",
            "caller": payload.caller,
            "callee": payload.callee,
            "sip_to": payload.sip_to,
            "sip_from": payload.sip_from,
            "resolved_called_number": resolved_candidate,
        },
    )

    session.add(call_session)
    session.commit()
    session.refresh(call_session)

    instructions = build_realtime_instructions(context)
    if config.call_audio_mode == "vps_media_bridge" and config.voice_provider != "openai":
        instructions = (
            f"{instructions}\n\n# Estado real de esta llamada\n"
            f"El gateway ya ha reproducido externamente este saludo: "
            f"{config.first_message!r}. No lo repitas ni vuelvas a presentarte "
            "salvo que la persona lo pida expresamente. Espera a que la persona "
            "hable y responde a su petición concreta.\n"
            "Continúa exactamente en el mismo idioma del saludo inicial. "
            f"Si el idioma configurado `{config.language}` no coincide con ese "
            "saludo, prevalece el idioma del saludo para evitar cambios de idioma "
            "durante la llamada. El locale o el nombre de la voz TTS son solo "
            "metadatos de síntesis y nunca deben cambiar el idioma."
        )
    instructions = (
        f"{instructions}\n\n# Contexto técnico\n"
        f"clinic_id técnico de esta llamada: {context.clinic.id}. "
        "No lo leas en voz alta.\n"
        f"call_session_id técnico de esta llamada: {call_session.id}. "
        "No lo leas en voz alta."
    )

    return VoiceContextResponse(
        clinic_id=context.clinic.id,
        call_session_id=call_session.id,
        phone_number_id=context.phone_number.id if context.phone_number else None,
        assistant_config_id=config.id,
        model=config.realtime_model,
        realtime_voice=config.realtime_voice,
        call_audio_mode=config.call_audio_mode,
        voice_provider=config.voice_provider,
        tts_model=config.tts_model,
        voice_id=config.voice_id,
        voice_locale=config.voice_locale,
        voice_gender=config.voice_gender,
        azure_speech_region=config.azure_speech_region,
        voice_style=config.voice_style,
        voice_speed=str(config.voice_speed),
        voice_pitch=str(config.voice_pitch),
        voice_stability=_decimal_to_str(config.voice_stability),
        voice_similarity=_decimal_to_str(config.voice_similarity),
        voice_temperature=_decimal_to_str(config.voice_temperature),
        output_audio_format=config.output_audio_format,
        telephony_codec=config.telephony_codec,
        preview_audio_format=config.preview_audio_format,
        allow_interruptions=config.allow_interruptions,
        idle_timeout_ms=config.idle_timeout_ms,
        transcript_enabled=config.transcript_enabled,
        language=config.language,
        first_message=config.first_message,
        instructions=instructions,
        prompt=instructions,
        caller=caller_phone,
        called_number=called_number,
        resolved_called_number=resolved_candidate,
        clinic=_clinic_info(context.clinic),
        tools=list(get_realtime_tools()),
    )


@router.post("/tts")
def synthesize_internal_voice(
    payload: InternalTTSRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Generate finite TTS audio for the media bridge."""
    voice = (
        payload.voice_id
        if payload.voice_provider != "openai" and payload.voice_id
        else payload.realtime_voice
    )
    try:
        result = synthesize_speech(
            settings,
            provider=payload.voice_provider,
            text=payload.text,
            voice=voice,
            model=payload.tts_model,
            response_format=payload.preview_audio_format,
            output_audio_format=payload.output_audio_format,
            telephony_codec=payload.telephony_codec,
            locale=payload.voice_locale,
            gender=payload.voice_gender,
            provider_region=payload.azure_speech_region,
            voice_style=payload.voice_style,
            voice_speed=payload.voice_speed,
            voice_pitch=payload.voice_pitch,
            voice_stability=payload.voice_stability,
            voice_similarity=payload.voice_similarity,
            voice_temperature=payload.voice_temperature,
            instructions=build_voice_instruction_block(payload),
        )
    except TTSGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return Response(content=result.audio, media_type=result.media_type)


@router.post("/tool")
def execute_internal_voice_tool(
    payload: InternalToolRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Execute one existing assistant tool for the VPS media bridge."""
    context = ToolExecutionContext(
        settings=settings,
        session_factory=get_session_factory(),
        call_session_id=payload.call_session_id,
        clinic_id=payload.clinic_id,
        openai_call_id=payload.openai_call_id,
    )
    return execute_realtime_tool(payload.name, payload.arguments, context)
