"""Call management API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CallSession
from app.schemas import CallDeleteResponse, ComponentStatus

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("/status", response_model=ComponentStatus)
def calls_status() -> ComponentStatus:
    """Expose the current call integration implementation status."""
    return ComponentStatus(component="openai_realtime", status="ready")


@router.delete(
    "/{call_session_id}",
    response_model=CallDeleteResponse,
)
def delete_call_session(
    call_session_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CallDeleteResponse:
    """Delete one call and cascade its diagnostic events."""
    call_session = session.get(CallSession, call_session_id)
    if call_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call session not found.",
        )
    session.delete(call_session)
    session.commit()
    return CallDeleteResponse(
        status="deleted",
        call_session_id=call_session_id,
    )
