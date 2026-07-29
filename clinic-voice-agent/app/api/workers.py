"""Worker calendar provisioning endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.calendar.google_client import (
    CalendarInfo,
    GoogleAuthorizationRequired,
    WorkerCalendarError,
    create_calendar_for_worker,
    get_authorized_calendar_client,
    link_calendar_to_worker,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Worker
from app.schemas import (
    CalendarInfoResponse,
    WorkerCalendarCreateRequest,
    WorkerCalendarLinkRequest,
    WorkerCalendarResponse,
)

router = APIRouter(prefix="/workers", tags=["workers"])


def _calendar_response(
    worker: Worker,
    calendar: CalendarInfo,
) -> WorkerCalendarResponse:
    """Map a worker and Google response to the public schema."""
    return WorkerCalendarResponse(
        worker_id=worker.id,
        calendar_id=calendar.id,
        color_id=worker.color_id,
        calendar=CalendarInfoResponse(
            id=calendar.id,
            summary=calendar.summary,
            primary=calendar.primary,
            access_role=calendar.access_role,
            color_id=calendar.color_id,
            background_color=calendar.background_color,
            foreground_color=calendar.foreground_color,
            time_zone=calendar.time_zone,
        ),
    )


def _get_worker(session: Session, worker_id: uuid.UUID) -> Worker:
    """Return an existing worker or raise a REST-friendly error."""
    worker = session.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker not found.",
        )
    return worker


@router.post(
    "/{worker_id}/create-calendar",
    response_model=WorkerCalendarResponse,
)
def create_worker_calendar(
    worker_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: Annotated[
        WorkerCalendarCreateRequest | None,
        Body(),
    ] = None,
) -> WorkerCalendarResponse:
    """Create a secondary calendar owned by the clinic Google account."""
    worker = _get_worker(session, worker_id)
    payload = payload or WorkerCalendarCreateRequest()
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            worker.clinic_id,
        )
        calendar = create_calendar_for_worker(
            session,
            client,
            worker,
            summary=payload.summary,
            color_id=payload.color_id,
        )
    except GoogleAuthorizationRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=str(exc),
        ) from exc
    except WorkerCalendarError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _calendar_response(worker, calendar)


@router.post(
    "/{worker_id}/link-calendar",
    response_model=WorkerCalendarResponse,
)
def link_worker_calendar(
    worker_id: uuid.UUID,
    payload: WorkerCalendarLinkRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkerCalendarResponse:
    """Link an existing writable Google Calendar to a worker."""
    worker = _get_worker(session, worker_id)
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            worker.clinic_id,
        )
        calendar = link_calendar_to_worker(
            session,
            client,
            worker,
            calendar_id=payload.calendar_id,
            color_id=payload.color_id,
        )
    except GoogleAuthorizationRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=str(exc),
        ) from exc
    except WorkerCalendarError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _calendar_response(worker, calendar)
