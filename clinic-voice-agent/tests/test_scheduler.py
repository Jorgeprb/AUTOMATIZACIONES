"""Scheduling-engine tests over mocked Google FreeBusy responses."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.calendar.scheduler import (
    ProposedSlot,
    build_working_ranges,
    check_slot_available,
    generate_candidate_slots,
    propose_slots,
)
from app.models import Clinic, Service, Worker

MADRID = ZoneInfo("Europe/Madrid")
MONDAY = date(2026, 6, 22)
NOW = datetime(2026, 6, 20, 8, 0, tzinfo=UTC)


def _weekly_hours(
    monday: list[dict[str, str]] | None = None,
    *,
    sunday: list[dict[str, str]] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Build a complete weekly schedule for tests."""
    return {
        "monday": monday or [],
        "tuesday": [],
        "wednesday": [],
        "thursday": [],
        "friday": [],
        "saturday": [],
        "sunday": sunday or [],
    }


def _create_clinic_service_workers(
    session: Session,
    *,
    working_hours: dict[str, list[dict[str, str]]],
    worker_count: int = 1,
    duration_minutes: int = 30,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
) -> tuple[Clinic, Service, list[Worker]]:
    """Persist a clinic, service, and linked workers."""
    clinic = Clinic(
        name="Clínica Scheduling",
        timezone="Europe/Madrid",
        phone_number=f"+3492{worker_count}{duration_minutes:03d}000",
    )
    service = Service(
        clinic=clinic,
        name="Consulta",
        duration_minutes=duration_minutes,
        buffer_before_minutes=buffer_before_minutes,
        buffer_after_minutes=buffer_after_minutes,
    )
    workers = [
        Worker(
            clinic=clinic,
            name=name,
            role="Médico",
            calendar_id=f"{name.lower()}@calendar.test",
            working_hours_json=working_hours,
        )
        for name in ("Ana", "Luis")[:worker_count]
    ]
    session.add_all([clinic, service, *workers])
    session.commit()
    return clinic, service, workers


def _freebusy_client(
    busy_by_calendar: dict[str, list[tuple[datetime, datetime]]],
) -> MagicMock:
    """Create a Google client mock that answers one FreeBusy request."""
    client = MagicMock()

    def execute() -> dict[str, Any]:
        request_body = client.freebusy.return_value.query.call_args.kwargs["body"]
        return {
            "calendars": {
                item["id"]: {
                    "busy": [
                        {
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                        }
                        for start, end in busy_by_calendar.get(item["id"], [])
                    ]
                }
                for item in request_body["items"]
            }
        }

    client.freebusy.return_value.query.return_value.execute.side_effect = execute
    return client


def _starts(slots: list[ProposedSlot]) -> list[str]:
    """Return local HH:MM values for compact assertions."""
    return [slot.start_at.strftime("%H:%M") for slot in slots]


def test_worker_free_all_day_returns_first_three_slots(
    db_session: Session,
) -> None:
    """A fully free worker should produce real chronological slots."""
    clinic, service, workers = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours([{"start": "09:00", "end": "17:00"}]),
    )

    slots = propose_slots(
        db_session,
        _freebusy_client({}),
        clinic_id=clinic.id,
        service_id=service.id,
        worker_id=workers[0].id,
        preferred_date=MONDAY,
        now=NOW,
    )

    assert _starts(slots) == ["09:00", "09:15", "09:30"]
    assert all(slot.start_at.tzinfo is not None for slot in slots)


def test_partially_busy_worker_only_returns_remaining_ranges(
    db_session: Session,
) -> None:
    """Busy periods must be subtracted without inventing overlaps."""
    clinic, service, workers = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours([{"start": "09:00", "end": "12:00"}]),
    )
    busy_start = datetime(2026, 6, 22, 9, 0, tzinfo=MADRID)
    busy_end = datetime(2026, 6, 22, 10, 30, tzinfo=MADRID)

    slots = propose_slots(
        db_session,
        _freebusy_client(
            {workers[0].calendar_id: [(busy_start, busy_end)]}  # type: ignore[dict-item]
        ),
        clinic_id=clinic.id,
        service_id=service.id,
        worker_id=workers[0].id,
        preferred_date=MONDAY,
        now=NOW,
    )

    assert _starts(slots) == ["10:30", "10:45", "11:00"]
    assert all(slot.start_at >= busy_end for slot in slots)


def test_two_workers_can_offer_overlapping_slots(
    db_session: Session,
) -> None:
    """Independent calendars may offer the same start time simultaneously."""
    clinic, service, workers = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours([{"start": "09:00", "end": "11:00"}]),
        worker_count=2,
    )

    slots = propose_slots(
        db_session,
        _freebusy_client({}),
        clinic_id=clinic.id,
        service_id=service.id,
        preferred_date=MONDAY,
        max_slots=2,
        now=NOW,
    )

    assert _starts(slots) == ["09:00", "09:00"]
    assert {slot.worker_id for slot in slots} == {
        workers[0].id,
        workers[1].id,
    }


@pytest.mark.parametrize(
    ("preference", "expected_start"),
    [
        ("morning", "09:00"),
        ("afternoon", "16:00"),
        ("16:30-17:30", "16:30"),
    ],
)
def test_named_time_window_preferences(
    db_session: Session,
    preference: str,
    expected_start: str,
) -> None:
    """Morning and afternoon preferences should rank matching slots first."""
    clinic, service, _ = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours(
            [
                {"start": "09:00", "end": "12:00"},
                {"start": "16:00", "end": "20:00"},
            ]
        ),
    )

    slots = propose_slots(
        db_session,
        _freebusy_client({}),
        clinic_id=clinic.id,
        service_id=service.id,
        preferred_date=MONDAY,
        preferred_time_window=preference,
        max_slots=1,
        now=NOW,
    )

    assert _starts(slots) == [expected_start]


def test_no_slots_when_entire_working_day_is_busy(
    db_session: Session,
) -> None:
    """A fully occupied worker must produce no proposals."""
    clinic, service, workers = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours([{"start": "09:00", "end": "11:00"}]),
    )
    busy = (
        datetime(2026, 6, 22, 9, 0, tzinfo=MADRID),
        datetime(2026, 6, 22, 11, 0, tzinfo=MADRID),
    )

    slots = propose_slots(
        db_session,
        _freebusy_client(
            {workers[0].calendar_id: [busy]}  # type: ignore[dict-item]
        ),
        clinic_id=clinic.id,
        service_id=service.id,
        preferred_date=MONDAY,
        days_ahead=1,
        now=NOW,
    )

    assert slots == []


def test_buffers_are_reserved_around_service_duration(
    db_session: Session,
) -> None:
    """Before/after buffers must fit and remain clear around the appointment."""
    clinic, service, workers = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours([{"start": "09:00", "end": "11:00"}]),
        buffer_before_minutes=15,
        buffer_after_minutes=15,
    )
    busy = (
        datetime(2026, 6, 22, 10, 0, tzinfo=MADRID),
        datetime(2026, 6, 22, 10, 30, tzinfo=MADRID),
    )

    slots = propose_slots(
        db_session,
        _freebusy_client(
            {workers[0].calendar_id: [busy]}  # type: ignore[dict-item]
        ),
        clinic_id=clinic.id,
        service_id=service.id,
        worker_id=workers[0].id,
        preferred_date=MONDAY,
        days_ahead=1,
        now=NOW,
    )

    assert _starts(slots) == ["09:15"]
    assert slots[0].blocked_start_at.strftime("%H:%M") == "09:00"
    assert slots[0].end_at.strftime("%H:%M") == "09:45"
    assert slots[0].blocked_end_at.strftime("%H:%M") == "10:00"


def test_europe_madrid_dst_change_never_generates_nonexistent_times() -> None:
    """Spring-forward scheduling should skip Madrid's missing 02:00 hour."""
    worker = Worker(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        clinic_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        name="Ana",
        role="Médica",
        calendar_id="ana@calendar.test",
        working_hours_json=_weekly_hours(sunday=[{"start": "01:00", "end": "04:00"}]),
    )

    ranges = build_working_ranges(
        worker,
        start_date=date(2026, 3, 29),
        days_ahead=1,
        timezone="Europe/Madrid",
    )

    assert len(ranges) == 1
    assert ranges[0].end - ranges[0].start == timedelta(hours=2)
    local_start = ranges[0].start.astimezone(MADRID)
    local_end = ranges[0].end.astimezone(MADRID)
    assert local_start.strftime("%H:%M %z") == "01:00 +0100"
    assert local_end.strftime("%H:%M %z") == "04:00 +0200"
    slots = generate_candidate_slots(
        worker,
        available_ranges=ranges,
        duration_minutes=30,
        timezone="Europe/Madrid",
    )
    assert slots
    assert all(slot.start_at.hour != 2 for slot in slots)


def test_check_slot_available_performs_final_freebusy_check(
    db_session: Session,
) -> None:
    """The booking guard should check both working hours and Google again."""
    _, _, workers = _create_clinic_service_workers(
        db_session,
        working_hours=_weekly_hours([{"start": "09:00", "end": "12:00"}]),
    )
    worker = workers[0]
    start_at = datetime(2026, 6, 22, 9, 0, tzinfo=MADRID)
    end_at = start_at + timedelta(minutes=30)
    free_client = _freebusy_client({})
    busy_client = _freebusy_client(
        {worker.calendar_id: [(start_at, end_at)]}  # type: ignore[dict-item]
    )

    assert check_slot_available(
        free_client,
        worker=worker,
        start_at=start_at,
        end_at=end_at,
        timezone="Europe/Madrid",
    )
    assert not check_slot_available(
        busy_client,
        worker=worker,
        start_at=start_at,
        end_at=end_at,
        timezone="Europe/Madrid",
    )
