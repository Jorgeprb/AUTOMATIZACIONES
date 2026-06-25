"""Small in-memory Google Calendar substitute for local simulation."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from datetime import datetime
from threading import RLock
from typing import Any


def _parse_datetime(value: str) -> datetime:
    """Parse Google-style RFC3339 values."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class FakeCalendarRequest:
    """Object with the same final `.execute()` shape as Google requests."""

    def __init__(self, execute: Callable[[], Any]) -> None:
        self._execute = execute

    def execute(self) -> Any:
        """Run the stored in-memory operation."""
        return self._execute()


class InMemoryCalendarBackend:
    """Thread-safe event store shared by fake calendar clients."""

    def __init__(self) -> None:
        self._events: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = RLock()

    def clear(self) -> None:
        """Remove all fake events."""
        with self._lock:
            self._events.clear()

    def insert_event(
        self,
        calendar_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert and return one copied fake event."""
        with self._lock:
            stored = copy.deepcopy(event)
            event_id = str(stored.get("id") or uuid.uuid4().hex)
            stored["id"] = event_id
            self._events.setdefault(calendar_id, {})[event_id] = stored
            return copy.deepcopy(stored)

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete an event when present."""
        with self._lock:
            self._events.get(calendar_id, {}).pop(event_id, None)

    def add_busy(
        self,
        calendar_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
        summary: str = "Ocupado",
    ) -> str:
        """Create a fake busy event useful in tests and demos."""
        event = self.insert_event(
            calendar_id,
            {
                "summary": summary,
                "start": {"dateTime": start_at.isoformat()},
                "end": {"dateTime": end_at.isoformat()},
            },
        )
        return str(event["id"])

    def list_events(self, calendar_id: str | None = None) -> list[dict[str, Any]]:
        """Return copies of all events, optionally for one calendar."""
        with self._lock:
            if calendar_id is not None:
                return [
                    copy.deepcopy(event)
                    for event in self._events.get(calendar_id, {}).values()
                ]
            return [
                copy.deepcopy(event)
                for calendar_events in self._events.values()
                for event in calendar_events.values()
            ]

    def freebusy(self, body: dict[str, Any]) -> dict[str, Any]:
        """Build a Google-compatible FreeBusy response."""
        time_min = _parse_datetime(str(body["timeMin"]))
        time_max = _parse_datetime(str(body["timeMax"]))
        calendars: dict[str, Any] = {}
        with self._lock:
            for item in body.get("items", []):
                calendar_id = str(item["id"])
                busy: list[dict[str, str]] = []
                for event in self._events.get(calendar_id, {}).values():
                    start_value = event.get("start", {}).get("dateTime")
                    end_value = event.get("end", {}).get("dateTime")
                    if not start_value or not end_value:
                        continue
                    start_at = _parse_datetime(str(start_value))
                    end_at = _parse_datetime(str(end_value))
                    if start_at < time_max and time_min < end_at:
                        busy.append(
                            {
                                "start": start_at.isoformat(),
                                "end": end_at.isoformat(),
                            }
                        )
                calendars[calendar_id] = {"busy": busy}
        return {"calendars": calendars}


class FakeFreeBusyResource:
    """Fake `freebusy()` resource."""

    def __init__(self, backend: InMemoryCalendarBackend) -> None:
        self._backend = backend

    def query(self, *, body: dict[str, Any]) -> FakeCalendarRequest:
        """Return a deferred FreeBusy query."""
        return FakeCalendarRequest(lambda: self._backend.freebusy(body))


class FakeEventsResource:
    """Fake `events()` resource."""

    def __init__(self, backend: InMemoryCalendarBackend) -> None:
        self._backend = backend

    def insert(
        self,
        *,
        calendarId: str,
        body: dict[str, Any],
    ) -> FakeCalendarRequest:
        """Return a deferred event insertion."""
        return FakeCalendarRequest(lambda: self._backend.insert_event(calendarId, body))

    def delete(
        self,
        *,
        calendarId: str,
        eventId: str,
        sendUpdates: str = "none",
    ) -> FakeCalendarRequest:
        """Return a deferred event deletion."""
        del sendUpdates
        return FakeCalendarRequest(
            lambda: self._backend.delete_event(calendarId, eventId)
        )


class FakeGoogleCalendarClient:
    """Calendar client subset used by scheduling and appointments."""

    def __init__(self, backend: InMemoryCalendarBackend) -> None:
        self.backend = backend
        self._freebusy = FakeFreeBusyResource(backend)
        self._events = FakeEventsResource(backend)

    def freebusy(self) -> FakeFreeBusyResource:
        """Return the fake FreeBusy resource."""
        return self._freebusy

    def events(self) -> FakeEventsResource:
        """Return the fake Events resource."""
        return self._events


default_fake_calendar_backend = InMemoryCalendarBackend()
