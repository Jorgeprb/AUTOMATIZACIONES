"""Admin endpoints for browser Realtime voice previews."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.admin_schemas import (
    CallAudioMode,
    RealtimePreviewHeartbeatResponse,
    RealtimePreviewSessionCreate,
    RealtimePreviewSessionResponse,
    RealtimePreviewToolCallRequest,
    RealtimePreviewToolCallResponse,
    VoiceProvider,
)
from app.api.admin.common import clinic_or_404
from app.config import Settings, get_settings
from app.db import get_db, get_session_factory
from app.realtime_preview import (
    RealtimePreviewError,
    close_preview_session,
    execute_preview_tool,
    heartbeat_preview_session,
    start_realtime_preview_session,
)

router = APIRouter(prefix="/admin", tags=["Admin · Assistant configs"])


@router.post(
    "/clinics/{clinic_id}/assistant-configs/realtime-preview-sessions",
    response_model=RealtimePreviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_realtime_preview_session(
    clinic_id: uuid.UUID,
    payload: RealtimePreviewSessionCreate,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RealtimePreviewSessionResponse:
    """Create one ephemeral OpenAI Realtime session for browser microphone tests."""
    clinic_or_404(session, clinic_id)
    try:
        entry, client_secret, initial_message = start_realtime_preview_session(
            session,
            get_session_factory(),
            settings,
            clinic_id=clinic_id,
            assistant_config_id=payload.assistant_config_id,
            payload=payload.config,
        )
    except RealtimePreviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return RealtimePreviewSessionResponse(
        id=entry.id,
        call_session_id=entry.call_session_id,
        client_secret=client_secret,
        model=entry.model,
        voice=entry.voice,
        call_audio_mode=cast(CallAudioMode, entry.call_audio_mode),
        voice_provider=cast(VoiceProvider, entry.voice_provider),
        external_tts_required=(
            entry.call_audio_mode == "vps_media_bridge"
            or entry.voice_provider != "openai"
        ),
        initial_message=initial_message,
        expires_at=entry.expires_at,
    )


@router.post(
    "/realtime-preview-sessions/{session_id}/heartbeat",
    response_model=RealtimePreviewHeartbeatResponse,
)
def heartbeat_realtime_preview_session(
    session_id: uuid.UUID,
) -> RealtimePreviewHeartbeatResponse:
    """Keep one browser Realtime preview alive while the page is open."""
    try:
        entry = heartbeat_preview_session(get_session_factory(), session_id)
    except RealtimePreviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(exc),
        ) from exc
    return RealtimePreviewHeartbeatResponse(ok=True, expires_at=entry.expires_at)


@router.post(
    "/realtime-preview-sessions/{session_id}/tool-call",
    response_model=RealtimePreviewToolCallResponse,
)
def execute_realtime_preview_tool_call(
    session_id: uuid.UUID,
    payload: RealtimePreviewToolCallRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RealtimePreviewToolCallResponse:
    """Execute one tool call emitted by the Realtime preview data channel."""
    try:
        output = execute_preview_tool(
            get_session_factory(),
            settings,
            preview_session_id=session_id,
            name=payload.name,
            arguments=payload.arguments,
        )
    except RealtimePreviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(exc),
        ) from exc
    return RealtimePreviewToolCallResponse(call_id=payload.call_id, output=output)


@router.delete(
    "/realtime-preview-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def close_realtime_preview_session(session_id: uuid.UUID) -> None:
    """Invalidate one browser Realtime preview session."""
    close_preview_session(get_session_factory(), session_id)
