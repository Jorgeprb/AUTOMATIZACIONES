"""Admin endpoints for browser Realtime voice previews."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.admin_schemas import (
    CallAudioMode,
    RealtimePreviewHeartbeatResponse,
    RealtimePreviewSessionCreate,
    RealtimePreviewSessionResponse,
    RealtimePreviewStopRequest,
    RealtimePreviewToolCallRequest,
    RealtimePreviewToolCallResponse,
    VoiceProvider,
)
from app.api.admin.common import clinic_or_404
from app.auth import AdminPrincipal
from app.config import Settings, get_settings
from app.db import get_db
from app.realtime_preview import (
    RealtimePreviewError,
    RealtimePreviewRegistryEntry,
    close_preview_session,
    execute_preview_tool,
    get_preview_entry,
    heartbeat_preview_session,
    start_realtime_preview_session,
)
from app.utils.security import require_admin_access

router = APIRouter(prefix="/admin", tags=["Admin · Assistant configs"])


def _factory(session: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=session.get_bind(),
        class_=Session,
        expire_on_commit=False,
    )


def _require_preview_access(
    entry: RealtimePreviewRegistryEntry,
    principal: AdminPrincipal,
) -> None:
    if not principal.can_access_clinic(entry.clinic_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this clinic.",
        )
    if not principal.can_write_clinic(entry.clinic_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have read-only access to this clinic.",
        )


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
            _factory(session),
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
    "/clinics/{clinic_id}/assistant-configs/realtime-test/start",
    response_model=RealtimePreviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_realtime_test_session(
    clinic_id: uuid.UUID,
    payload: RealtimePreviewSessionCreate,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RealtimePreviewSessionResponse:
    """Compatibility alias for UI Realtime microphone tests."""
    return create_realtime_preview_session(
        clinic_id=clinic_id,
        payload=payload,
        session=session,
        settings=settings,
    )


@router.post(
    "/realtime-preview-sessions/{session_id}/heartbeat",
    response_model=RealtimePreviewHeartbeatResponse,
)
def heartbeat_realtime_preview_session(
    session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> RealtimePreviewHeartbeatResponse:
    """Keep one browser Realtime preview alive while the page is open."""
    try:
        factory = _factory(session)
        entry = get_preview_entry(factory, session_id)
        _require_preview_access(entry, principal)
        entry = heartbeat_preview_session(factory, session_id)
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
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> RealtimePreviewToolCallResponse:
    """Execute one tool call emitted by the Realtime preview data channel."""
    try:
        factory = _factory(session)
        entry = get_preview_entry(factory, session_id)
        _require_preview_access(entry, principal)
        output = execute_preview_tool(
            factory,
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
def close_realtime_preview_session(
    session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> None:
    """Invalidate one browser Realtime preview session."""
    factory = _factory(session)
    try:
        entry = get_preview_entry(factory, session_id)
    except RealtimePreviewError:
        return
    _require_preview_access(entry, principal)
    close_preview_session(factory, session_id)


@router.post(
    "/clinics/{clinic_id}/assistant-configs/realtime-test/stop",
    status_code=status.HTTP_204_NO_CONTENT,
)
def stop_realtime_test_session(
    clinic_id: uuid.UUID,
    payload: RealtimePreviewStopRequest,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> None:
    """Compatibility alias to invalidate one browser Realtime preview session."""
    clinic_or_404(session, clinic_id)
    factory = _factory(session)
    try:
        entry = get_preview_entry(factory, payload.session_id)
    except RealtimePreviewError:
        return
    if entry.clinic_id != clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Realtime preview session not found.",
        )
    _require_preview_access(entry, principal)
    close_preview_session(factory, payload.session_id)
