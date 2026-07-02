"""Browser WebRTC preview sessions for AssistantConfig editing."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_schemas import AssistantConfigCreate
from app.config import Settings
from app.models import AssistantConfig, CallEvent, CallSession, CallStatus, Clinic
from app.openai_realtime.prompt_builder import (
    ActiveAssistantConfigMissing,
    build_clinic_context,
    build_realtime_instructions,
)
from app.openai_realtime.session import RealtimeSessionConfig
from app.openai_realtime.tools import ToolExecutionContext, execute_realtime_tool

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
OPENAI_REALTIME_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"
PREVIEW_SESSION_TTL_SECONDS = 120


class RealtimePreviewError(RuntimeError):
    """Stable error for the browser Realtime preview flow."""


@dataclass(slots=True)
class RealtimePreviewRegistryEntry:
    """In-memory state for one browser-owned Realtime preview."""

    id: uuid.UUID
    clinic_id: uuid.UUID
    call_session_id: uuid.UUID
    model: str
    voice: str
    expires_at: datetime
    closed: bool = False


_REGISTRY: dict[uuid.UUID, RealtimePreviewRegistryEntry] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _session_headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }


def _temporary_assistant_config(
    clinic_id: uuid.UUID,
    payload: AssistantConfigCreate,
    *,
    config_id: uuid.UUID | None = None,
) -> AssistantConfig:
    """Build a non-persisted AssistantConfig from current form values."""
    config = AssistantConfig(
        clinic_id=clinic_id,
        **payload.model_dump(),
    )
    if config_id is not None:
        config.id = config_id
    return config


def _build_preview_session_config(
    session: Session,
    settings: Settings,
    *,
    clinic_id: uuid.UUID,
    assistant_config_id: uuid.UUID | None,
    payload: AssistantConfigCreate,
    call_session_id: uuid.UUID,
) -> RealtimeSessionConfig:
    """Render the exact Realtime session config using unsaved form values."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise RealtimePreviewError("Clínica no encontrada.")
    if assistant_config_id is None:
        assistant_config_id = session.scalar(
            select(AssistantConfig.id).where(
                AssistantConfig.clinic_id == clinic_id,
                AssistantConfig.is_active.is_(True),
            )
        )
    if assistant_config_id is None:
        raise ActiveAssistantConfigMissing(
            "La clínica no tiene configuración base activa."
        )
    context = build_clinic_context(
        session,
        clinic_id=clinic_id,
        assistant_config_id=assistant_config_id,
    )
    temp_config = _temporary_assistant_config(
        clinic_id,
        payload,
        config_id=assistant_config_id,
    )
    context = replace(context, active_assistant_config=temp_config)
    instructions = build_realtime_instructions(context)
    instructions = (
        f"{instructions}\n\n# Contexto técnico\n"
        f"clinic_id real: {clinic_id}. No lo leas en voz alta.\n"
        f"call_session_id de esta prueba: {call_session_id}. No lo leas en voz alta.\n"
        "Esta es una prueba de configuración desde navegador. Usa las mismas "
        "herramientas y reglas que una llamada real."
    )
    return RealtimeSessionConfig(
        model=payload.realtime_model,
        voice=payload.realtime_voice,
        instructions=instructions,
        transcription_enabled=payload.transcript_enabled,
        language=payload.language,
        initial_message=payload.first_message,
        fallback_voice=payload.fallback_voice,
        allow_interruptions=payload.allow_interruptions,
        idle_timeout_ms=payload.idle_timeout_ms,
    )


def cleanup_expired_preview_sessions(session_factory: SessionFactory) -> None:
    """Close stale previews when any preview endpoint is touched."""
    now = _now()
    expired = [
        entry
        for entry in list(_REGISTRY.values())
        if entry.closed or entry.expires_at <= now
    ]
    if not expired:
        return
    with session_factory() as session:
        for entry in expired:
            call = session.get(CallSession, entry.call_session_id)
            if call is not None and call.status == CallStatus.ACTIVE:
                call.status = CallStatus.COMPLETED
                call.ended_at = now
                call.conversation_state_json = {
                    **call.conversation_state_json,
                    "realtime_preview_expired": True,
                }
                session.add(
                    CallEvent(
                        call_session_id=call.id,
                        event_type="assistant_config.preview.expired",
                        payload_json={"preview_session_id": str(entry.id)},
                    )
                )
        session.commit()
    for entry in expired:
        _REGISTRY.pop(entry.id, None)


def start_realtime_preview_session(
    session: Session,
    session_factory: SessionFactory,
    settings: Settings,
    *,
    clinic_id: uuid.UUID,
    assistant_config_id: uuid.UUID | None,
    payload: AssistantConfigCreate,
) -> tuple[RealtimePreviewRegistryEntry, str, str]:
    """Create an ephemeral OpenAI Realtime session for a browser WebRTC client."""
    cleanup_expired_preview_sessions(session_factory)
    preview_id = uuid.uuid4()
    now = _now()
    call = CallSession(
        clinic_id=clinic_id,
        assistant_config_id=assistant_config_id,
        openai_call_id=f"realtime-preview-{preview_id}",
        caller_phone="browser-preview",
        called_number="browser-preview",
        status=CallStatus.ACTIVE,
        transcript_enabled=False,
        recording_enabled=False,
        conversation_state_json={
            "realtime_preview": True,
            "preview_session_id": str(preview_id),
            "processed_tool_call_ids": [],
        },
    )
    session.add(call)
    session.flush()
    config = _build_preview_session_config(
        session,
        settings,
        clinic_id=clinic_id,
        assistant_config_id=assistant_config_id,
        payload=payload,
        call_session_id=call.id,
    )
    openai_payload = config.as_accept_payload()
    openai_payload.pop("type", None)
    try:
        response = httpx.post(
            OPENAI_REALTIME_SESSIONS_URL,
            headers=_session_headers(settings),
            json=openai_payload,
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        call.status = CallStatus.FAILED
        call.ended_at = now
        call.summary_text = "Realtime preview session could not be created."
        session.commit()
        logger.exception("realtime_preview_openai_session_failed")
        raise RealtimePreviewError(
            "OpenAI no pudo crear la sesión Realtime de prueba."
        ) from exc
    body = response.json()
    client_secret = body.get("client_secret")
    if isinstance(client_secret, dict):
        secret_value = client_secret.get("value")
    else:
        secret_value = None
    if not isinstance(secret_value, str) or not secret_value:
        call.status = CallStatus.FAILED
        call.ended_at = now
        call.summary_text = "OpenAI did not return a client secret."
        session.commit()
        raise RealtimePreviewError("OpenAI no devolvió client_secret.")
    expires_at = now + timedelta(seconds=PREVIEW_SESSION_TTL_SECONDS)
    entry = RealtimePreviewRegistryEntry(
        id=preview_id,
        clinic_id=clinic_id,
        call_session_id=call.id,
        model=config.model,
        voice=config.voice,
        expires_at=expires_at,
    )
    _REGISTRY[preview_id] = entry
    session.add(
        CallEvent(
            call_session_id=call.id,
            event_type="assistant_config.preview.opened",
            payload_json={
                "preview_session_id": str(preview_id),
                "model": config.model,
                "voice": config.voice,
            },
        )
    )
    session.commit()
    logger.info(
        "realtime_preview_opened",
        extra={
            "preview_session_id": str(preview_id),
            "clinic_id": str(clinic_id),
            "call_session_id": str(call.id),
        },
    )
    return entry, secret_value, config.initial_message or payload.first_message


def get_preview_entry(
    session_factory: SessionFactory,
    preview_session_id: uuid.UUID,
) -> RealtimePreviewRegistryEntry:
    """Return a live preview entry or raise a stable error."""
    cleanup_expired_preview_sessions(session_factory)
    entry = _REGISTRY.get(preview_session_id)
    if entry is None or entry.closed or entry.expires_at <= _now():
        raise RealtimePreviewError("La sesión Realtime de prueba ya está cerrada.")
    return entry


def heartbeat_preview_session(
    session_factory: SessionFactory,
    preview_session_id: uuid.UUID,
) -> RealtimePreviewRegistryEntry:
    """Extend one preview session while the browser is alive."""
    entry = get_preview_entry(session_factory, preview_session_id)
    entry.expires_at = _now() + timedelta(seconds=PREVIEW_SESSION_TTL_SECONDS)
    return entry


def execute_preview_tool(
    session_factory: SessionFactory,
    settings: Settings,
    *,
    preview_session_id: uuid.UUID,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute one model tool call for a browser Realtime preview."""
    entry = heartbeat_preview_session(session_factory, preview_session_id)
    context = ToolExecutionContext(
        settings=settings,
        session_factory=session_factory,
        call_session_id=entry.call_session_id,
        clinic_id=entry.clinic_id,
        openai_call_id=f"realtime-preview-{entry.id}",
    )
    result = execute_realtime_tool(name, arguments, context)
    with session_factory() as session:
        session.add(
            CallEvent(
                call_session_id=entry.call_session_id,
                event_type="assistant_config.preview.tool_call",
                payload_json={
                    "preview_session_id": str(entry.id),
                    "tool_name": name,
                    "result_ok": bool(result.get("ok")),
                },
            )
        )
        session.commit()
    return result


def close_preview_session(
    session_factory: SessionFactory,
    preview_session_id: uuid.UUID,
    *,
    reason: str = "closed_by_browser",
) -> None:
    """Mark a preview session closed and stop accepting tool calls."""
    entry = _REGISTRY.pop(preview_session_id, None)
    if entry is None:
        return
    entry.closed = True
    now = _now()
    with session_factory() as session:
        call = session.get(CallSession, entry.call_session_id)
        if call is not None:
            if call.status == CallStatus.ACTIVE:
                call.status = CallStatus.COMPLETED
            call.ended_at = call.ended_at or now
            call.conversation_state_json = {
                **call.conversation_state_json,
                "realtime_preview_closed": True,
                "realtime_preview_close_reason": reason,
            }
            session.add(
                CallEvent(
                    call_session_id=call.id,
                    event_type="assistant_config.preview.closed",
                    payload_json={
                        "preview_session_id": str(preview_session_id),
                        "reason": reason,
                    },
                )
            )
        session.commit()
    logger.info(
        "realtime_preview_closed",
        extra={"preview_session_id": str(preview_session_id), "reason": reason},
    )
