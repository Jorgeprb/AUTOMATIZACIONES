"""Authorized Google Calendar client and calendar management operations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, cast

from cryptography.fernet import InvalidToken
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar.auth import GOOGLE_CALENDAR_SCOPES
from app.config import Settings
from app.models import Clinic, GoogleCredential, Worker
from app.utils.security import TokenCipher


class GoogleCalendarError(RuntimeError):
    """Base exception for Calendar integration failures."""


class GoogleAuthorizationRequired(GoogleCalendarError):
    """Raised when a clinic must complete OAuth again."""


class WorkerCalendarError(GoogleCalendarError):
    """Raised when a worker calendar cannot be created or linked."""


class GoogleCalendarClient(Protocol):
    """Dynamic subset exposed by the Google Calendar discovery client."""

    def calendars(self) -> Any:
        """Return the calendars resource."""
        ...

    def calendarList(self) -> Any:
        """Return the user's calendar-list resource."""
        ...

    def colors(self) -> Any:
        """Return the colors resource."""
        ...

    def events(self) -> Any:
        """Return the events resource."""
        ...

    def freebusy(self) -> Any:
        """Return the free/busy resource."""
        ...


@dataclass(frozen=True, slots=True)
class CalendarInfo:
    """Calendar metadata exposed to API consumers."""

    id: str
    summary: str
    primary: bool
    access_role: str | None
    color_id: str | None
    background_color: str | None
    foreground_color: str | None
    time_zone: str | None


@dataclass(frozen=True, slots=True)
class EventColor:
    """One event color available in Google Calendar."""

    id: str
    background: str
    foreground: str


def get_stored_google_credential(
    session: Session,
    clinic_id: uuid.UUID,
) -> GoogleCredential | None:
    """Return the clinic's single stored credential, if connected."""
    return session.scalar(
        select(GoogleCredential).where(GoogleCredential.clinic_id == clinic_id)
    )


def get_authorized_google_credentials(
    session: Session,
    settings: Settings,
    clinic_id: uuid.UUID,
) -> Credentials:
    """Decrypt credentials and refresh them transparently when expired."""
    stored = get_stored_google_credential(session, clinic_id)
    if stored is None:
        raise GoogleAuthorizationRequired(
            "The clinic has not connected a Google account."
        )

    try:
        credentials_json = TokenCipher(
            settings.google_token_encryption_key.get_secret_value()
        ).decrypt(stored.token_json_encrypted)
        credentials = Credentials.from_authorized_user_info(
            json.loads(credentials_json),
            scopes=GOOGLE_CALENDAR_SCOPES,
        )
    except (InvalidToken, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GoogleAuthorizationRequired(
            "Stored Google credentials are invalid."
        ) from exc

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            raise GoogleAuthorizationRequired(
                "Google authorization has expired or was revoked."
            ) from exc
        stored.token_json_encrypted = TokenCipher(
            settings.google_token_encryption_key.get_secret_value()
        ).encrypt(credentials.to_json())
        session.commit()

    if not credentials.valid:
        raise GoogleAuthorizationRequired(
            "Google authorization must be completed again."
        )
    return credentials


def get_authorized_calendar_client(
    session: Session,
    settings: Settings,
    clinic_id: uuid.UUID,
) -> GoogleCalendarClient:
    """Build an authorized Calendar v3 discovery client."""
    credentials = get_authorized_google_credentials(
        session,
        settings,
        clinic_id,
    )
    return cast(
        GoogleCalendarClient,
        build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        ),
    )


def list_available_calendars(
    client: GoogleCalendarClient,
) -> list[CalendarInfo]:
    """List all calendars writable by the connected clinic account."""
    calendars: list[CalendarInfo] = []
    page_token: str | None = None
    while True:
        response = (
            client.calendarList()
            .list(
                maxResults=250,
                minAccessRole="writer",
                pageToken=page_token,
                showDeleted=False,
                showHidden=False,
            )
            .execute()
        )
        for item in response.get("items", []):
            calendars.append(
                CalendarInfo(
                    id=str(item["id"]),
                    summary=str(item.get("summary", item["id"])),
                    primary=bool(item.get("primary", False)),
                    access_role=item.get("accessRole"),
                    color_id=item.get("colorId"),
                    background_color=item.get("backgroundColor"),
                    foreground_color=item.get("foregroundColor"),
                    time_zone=item.get("timeZone"),
                )
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            return calendars


def get_event_colors(client: GoogleCalendarClient) -> list[EventColor]:
    """Return the event color palette available to the account."""
    response = client.colors().get().execute()
    return [
        EventColor(
            id=str(color_id),
            background=str(values["background"]),
            foreground=str(values["foreground"]),
        )
        for color_id, values in response.get("event", {}).items()
    ]


def create_secondary_calendar(
    client: GoogleCalendarClient,
    *,
    summary: str,
    timezone: str,
) -> CalendarInfo:
    """Create a secondary calendar owned by the authenticated clinic account."""
    created = (
        client.calendars()
        .insert(
            body={
                "summary": summary,
                "timeZone": timezone,
            }
        )
        .execute()
    )
    return CalendarInfo(
        id=str(created["id"]),
        summary=str(created.get("summary", summary)),
        primary=False,
        access_role="owner",
        color_id=None,
        background_color=None,
        foreground_color=None,
        time_zone=created.get("timeZone", timezone),
    )


def create_calendar_for_worker(
    session: Session,
    client: GoogleCalendarClient,
    worker: Worker,
    *,
    summary: str | None = None,
    color_id: str | None = None,
) -> CalendarInfo:
    """Create and persist a dedicated secondary calendar for a worker."""
    clinic = session.get(Clinic, worker.clinic_id)
    if clinic is None:
        raise WorkerCalendarError("Worker clinic does not exist.")
    try:
        calendar = create_secondary_calendar(
            client,
            summary=summary or f"{clinic.name} - {worker.name}",
            timezone=clinic.timezone,
        )
    except HttpError as exc:
        raise WorkerCalendarError(
            "Google Calendar rechazó la creación del calendario del trabajador."
        ) from exc
    worker.calendar_id = calendar.id
    if color_id is not None:
        worker.color_id = color_id
    session.commit()
    return calendar


def link_calendar_to_worker(
    session: Session,
    client: GoogleCalendarClient,
    worker: Worker,
    *,
    calendar_id: str,
    color_id: str | None = None,
) -> CalendarInfo:
    """Validate a writable calendar and link it to a worker."""
    try:
        calendar_item = client.calendarList().get(calendarId=calendar_id).execute()
    except HttpError as exc:
        raise WorkerCalendarError(
            "No se pudo consultar el calendario seleccionado en Google."
        ) from exc
    access_role = calendar_item.get("accessRole")
    if access_role not in {"owner", "writer"}:
        raise WorkerCalendarError(
            "The connected Google account cannot write to that calendar."
        )
    worker.calendar_id = str(calendar_item["id"])
    if color_id is not None:
        worker.color_id = color_id
    session.commit()
    return CalendarInfo(
        id=worker.calendar_id,
        summary=str(calendar_item.get("summary", worker.calendar_id)),
        primary=bool(calendar_item.get("primary", False)),
        access_role=access_role,
        color_id=calendar_item.get("colorId"),
        background_color=calendar_item.get("backgroundColor"),
        foreground_color=calendar_item.get("foregroundColor"),
        time_zone=calendar_item.get("timeZone"),
    )
