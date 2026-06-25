"""Google Calendar status and discovery endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calendar.google_client import (
    GoogleAuthorizationRequired,
    get_authorized_calendar_client,
    get_authorized_google_credentials,
    get_event_colors,
    get_stored_google_credential,
    list_available_calendars,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Clinic, Worker
from app.schemas import (
    CalendarInfoResponse,
    CalendarListResponse,
    CalendarStatusResponse,
    EventColorResponse,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _ensure_clinic(session: Session, clinic_id: uuid.UUID) -> Clinic:
    """Return an existing clinic or raise a REST-friendly error."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found.",
        )
    return clinic


@router.get("/status", response_model=CalendarStatusResponse)
def calendar_status(
    clinic_id: Annotated[uuid.UUID, Query()],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CalendarStatusResponse:
    """Report OAuth connectivity and worker calendar-link coverage."""
    _ensure_clinic(session, clinic_id)
    stored = get_stored_google_credential(session, clinic_id)
    connected = False
    needs_reauthorization = False
    if stored is not None:
        try:
            get_authorized_google_credentials(session, settings, clinic_id)
            connected = True
        except GoogleAuthorizationRequired:
            needs_reauthorization = True

    workers_total = session.scalar(
        select(func.count()).select_from(Worker).where(Worker.clinic_id == clinic_id)
    )
    workers_linked = session.scalar(
        select(func.count())
        .select_from(Worker)
        .where(
            Worker.clinic_id == clinic_id,
            Worker.calendar_id.is_not(None),
        )
    )
    return CalendarStatusResponse(
        clinic_id=clinic_id,
        connected=connected,
        needs_reauthorization=needs_reauthorization,
        account_email=stored.account_email if stored else None,
        workers_total=workers_total or 0,
        workers_linked=workers_linked or 0,
    )


@router.get("/list", response_model=CalendarListResponse)
def list_calendars(
    clinic_id: Annotated[uuid.UUID, Query()],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CalendarListResponse:
    """List writable calendars and available event colors."""
    _ensure_clinic(session, clinic_id)
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            clinic_id,
        )
    except GoogleAuthorizationRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    calendars = list_available_calendars(client)
    colors = get_event_colors(client)
    return CalendarListResponse(
        calendars=[
            CalendarInfoResponse(
                id=calendar.id,
                summary=calendar.summary,
                primary=calendar.primary,
                access_role=calendar.access_role,
                color_id=calendar.color_id,
                background_color=calendar.background_color,
                foreground_color=calendar.foreground_color,
                time_zone=calendar.time_zone,
            )
            for calendar in calendars
        ],
        event_colors=[
            EventColorResponse(
                id=color.id,
                background=color.background,
                foreground=color.foreground,
            )
            for color in colors
        ],
    )
