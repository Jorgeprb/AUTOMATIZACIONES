"""Internal voice gateway endpoints used by the VPS SIP media bridge."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audio import TTSGenerationError, synthesize_speech
from app.config import Settings, get_settings
from app.db import get_db, get_session_factory
from app.models import CallSession, CallStatus
from app.openai_realtime.prompt_builder import (
    ActiveAssistantConfigMissing,
    UnknownCalledNumber,
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

    called_number: str = Field(min_length=1, max_length=64)
    caller_phone: str = Field(default="", max_length=64)
    openai_call_id: str = Field(min_length=1, max_length=128)
    provider_call_id: str | None = Field(default=None, max_length=128)


class VoiceContextResponse(BaseModel):
    """Rendered assistant context consumed by sip-gateway."""

    clinic_id: uuid.UUID
    call_session_id: uuid.UUID
    phone_number_id: uuid.UUID | None
    assistant_config_id: uuid.UUID
    model: str
    realtime_voice: str
    voice_provider: str
    tts_model: str | None
    voice_id: str | None
    voice_locale: str | None
    voice_gender: str | None
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
    first_message: str
    instructions: str
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


@router.post("/context", response_model=VoiceContextResponse)
def create_voice_context(
    payload: VoiceContextRequest,
    session: Annotated[Session, Depends(get_db)],
) -> VoiceContextResponse:
    """Resolve DID to clinic context and create a CallSession for tools."""
    try:
        context = resolve_clinic_by_called_number(
            payload.called_number,
            session=session,
        )
    except UnknownCalledNumber as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ActiveAssistantConfigMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    config = context.active_assistant_config
    call_session = CallSession(
        clinic_id=context.clinic.id,
        phone_number_id=context.phone_number.id if context.phone_number else None,
        assistant_config_id=config.id,
        openai_call_id=payload.openai_call_id,
        provider_call_id=payload.provider_call_id,
        caller_phone=payload.caller_phone or "unknown",
        called_number=payload.called_number,
        status=CallStatus.ACTIVE,
        recording_enabled=config.recording_enabled,
        transcript_enabled=config.transcript_enabled,
        conversation_state_json={"source": "vps_media_bridge"},
    )
    session.add(call_session)
    session.commit()
    session.refresh(call_session)
    instructions = build_realtime_instructions(context)
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
        voice_provider=config.voice_provider,
        tts_model=config.tts_model,
        voice_id=config.voice_id,
        voice_locale=config.voice_locale,
        voice_gender=config.voice_gender,
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
        first_message=config.first_message,
        instructions=instructions,
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
