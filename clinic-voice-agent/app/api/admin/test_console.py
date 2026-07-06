"""Administrative browser test-console endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.admin_schemas import (
    DeleteResponse,
    TestSessionCreate,
    TestSessionMessageCreate,
    TestSessionRead,
    TestSessionTTSRequest,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import CallSession, TestSession
from app.test_console import (
    TestConsoleError,
    close_test_session,
    create_test_session,
    render_test_session,
    send_test_message,
    synthesize_test_session_audio,
)

router = APIRouter(prefix="/admin")


def _factory(session: Session) -> sessionmaker[Session]:
    """Create non-expiring sibling sessions bound to the request database."""
    return sessionmaker(
        bind=session.get_bind(),
        class_=Session,
        expire_on_commit=False,
    )


def _test_session_or_404(
    session: Session,
    session_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> TestSession:
    """Load one test session, optionally locking concurrent turns."""
    statement = select(TestSession).where(TestSession.id == session_id)
    if for_update:
        statement = statement.with_for_update()
    test_session = session.scalar(statement)
    if test_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test session not found.",
        )
    return test_session


@router.post(
    "/clinics/{clinic_id}/test-sessions",
    response_model=TestSessionRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Test console"],
)
def start_test_session(
    clinic_id: uuid.UUID,
    payload: TestSessionCreate,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestSessionRead:
    """Start a safe textual simulation for one clinic configuration."""
    try:
        test_session = create_test_session(
            session,
            _factory(session),
            settings,
            clinic_id=clinic_id,
            assistant_config_id=payload.assistant_config_id,
            use_real_calendar=payload.use_real_calendar,
            engine=payload.engine,
        )
        return render_test_session(session, test_session)
    except TestConsoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/test-sessions/{session_id}/message",
    response_model=TestSessionRead,
    tags=["Admin · Test console"],
)
def send_message(
    session_id: uuid.UUID,
    payload: TestSessionMessageCreate,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestSessionRead:
    """Process one patient message with the selected test engine."""
    test_session = _test_session_or_404(session, session_id, for_update=True)
    try:
        updated = send_test_message(
            session,
            _factory(session),
            settings,
            test_session,
            payload.message,
        )
        return render_test_session(session, updated)
    except TestConsoleError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/test-sessions/{session_id}",
    response_model=TestSessionRead,
    tags=["Admin · Test console"],
)
def get_test_session(
    session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> TestSessionRead:
    """Return the prompt, messages, tools, and extracted state."""
    try:
        return render_test_session(
            session,
            _test_session_or_404(session, session_id),
        )
    except TestConsoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/test-sessions/{session_id}/close",
    response_model=TestSessionRead,
    tags=["Admin · Test console"],
)
def close_session(
    session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> TestSessionRead:
    """Close a browser test conversation without deleting its trace."""
    test_session = _test_session_or_404(session, session_id, for_update=True)
    try:
        closed = close_test_session(session, test_session)
        return render_test_session(session, closed)
    except TestConsoleError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/test-sessions/{session_id}/tts",
    tags=["Admin · Test console"],
)
def synthesize_speech(
    session_id: uuid.UUID,
    payload: TestSessionTTSRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Generate finite TTS audio for one assistant message in the browser."""
    test_session = _test_session_or_404(session, session_id)
    try:
        generated = synthesize_test_session_audio(
            session,
            settings,
            test_session,
            payload.text,
        )
        if isinstance(generated, tuple):
            audio, media_type = generated
        else:
            audio = generated
            media_type = "audio/mpeg"
        return Response(content=audio, media_type=media_type)
    except TestConsoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/test-sessions/{session_id}",
    response_model=DeleteResponse,
    tags=["Admin · Test console"],
)
def delete_test_session(
    session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete browser state; real appointments remain untouched."""
    test_session = _test_session_or_404(session, session_id)
    raw_call_id = test_session.state_json.get("call_session_id")
    try:
        call_id = uuid.UUID(str(raw_call_id))
    except (TypeError, ValueError):
        call_id = None
    call = session.get(CallSession, call_id) if call_id is not None else None
    session.delete(test_session)
    if call is not None and not call.appointments:
        session.delete(call)
    session.commit()
    return DeleteResponse(id=session_id)
