"""Timezone-aware scheduling over working hours and Google FreeBusy data."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import islice
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar.google_client import GoogleCalendarClient, WorkerCalendarError
from app.models import AppointmentSource, Clinic, Service, Worker

SLOT_INTERVAL_MINUTES = 15
GOOGLE_FREEBUSY_CALENDAR_LIMIT = 50
WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
NAMED_TIME_WINDOWS = {
    "morning": (time(8, 0), time(14, 0)),
    "afternoon": (time(14, 0), time(18, 0)),
    "evening": (time(18, 0), time(22, 0)),
}
TIME_WINDOW_PATTERN = re.compile(
    r"^(?P<start_hour>[01]\d|2[0-3]):(?P<start_minute>[0-5]\d)-"
    r"(?P<end_hour>[01]\d|2[0-3]):(?P<end_minute>[0-5]\d)$"
)


class SchedulingError(RuntimeError):
    """Base exception for invalid or unavailable scheduling operations."""


class SchedulingValidationError(SchedulingError):
    """Raised when scheduling inputs or worker hours are invalid."""


class SchedulingProviderError(SchedulingError):
    """Raised when Google cannot provide reliable FreeBusy information."""


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A half-open, timezone-aware interval."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        _require_aware(self.start, "start")
        _require_aware(self.end, "end")
        if self.end <= self.start:
            raise SchedulingValidationError("Time range end must be after its start.")


@dataclass(frozen=True, slots=True)
class BusyPeriod:
    """An interval reported as busy by Google Calendar."""

    start: datetime
    end: datetime

    def as_range(self) -> TimeRange:
        """Return the busy period as a canonical range."""
        return TimeRange(self.start, self.end)


@dataclass(frozen=True, slots=True)
class ProposedSlot:
    """A real appointment option assigned to one worker."""

    worker_id: uuid.UUID
    worker_name: str
    calendar_id: str
    start_at: datetime
    end_at: datetime
    blocked_start_at: datetime
    blocked_end_at: datetime


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A preferred local wall-clock interval."""

    start: time
    end: time


T = TypeVar("T")


def _chunks(values: list[T], size: int) -> list[list[T]]:
    """Split values into fixed-size chunks."""
    iterator = iter(values)
    return [chunk for chunk in iter(lambda: list(islice(iterator, size)), []) if chunk]


def _require_aware(value: datetime, field_name: str) -> None:
    """Reject naive datetimes at integration boundaries."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchedulingValidationError(f"{field_name} must be timezone-aware.")


def _as_utc(value: datetime) -> datetime:
    """Normalize an aware datetime to UTC."""
    _require_aware(value, "datetime")
    return value.astimezone(UTC)


def _parse_clock(value: str, *, allow_24: bool = False) -> tuple[time, int]:
    """Parse `HH:MM`, returning the clock and an optional day offset."""
    if allow_24 and value == "24:00":
        return time(0, 0), 1
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise SchedulingValidationError(
            f"Invalid working-hours time: {value!r}."
        ) from exc
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise SchedulingValidationError(
            f"Working-hours time must use HH:MM: {value!r}."
        )
    return parsed, 0


def _localize_wall_time(
    day: date,
    clock: time,
    timezone: ZoneInfo,
    *,
    day_offset: int = 0,
    prefer_late_fold: bool = False,
) -> datetime:
    """Resolve a local wall time safely across DST transitions."""
    target_day = day + timedelta(days=day_offset)
    early = datetime.combine(target_day, clock, timezone).replace(fold=0)
    late = early.replace(fold=1)

    early_roundtrip = early.astimezone(UTC).astimezone(timezone)
    if early_roundtrip.replace(tzinfo=None) != early.replace(tzinfo=None):
        return early_roundtrip

    if early.utcoffset() != late.utcoffset() and prefer_late_fold:
        return late
    return early


def _merge_ranges(ranges: list[TimeRange]) -> list[TimeRange]:
    """Sort and merge overlapping or touching ranges in UTC."""
    normalized = sorted(
        (TimeRange(_as_utc(item.start), _as_utc(item.end)) for item in ranges),
        key=lambda item: item.start,
    )
    merged: list[TimeRange] = []
    for current in normalized:
        if not merged or current.start > merged[-1].end:
            merged.append(current)
            continue
        previous = merged[-1]
        merged[-1] = TimeRange(
            previous.start,
            max(previous.end, current.end),
        )
    return merged


def _parse_time_window(value: str | None) -> TimeWindow | None:
    """Parse a named or explicit preferred time window."""
    if value is None:
        return None
    normalized = value.strip().lower()
    named = NAMED_TIME_WINDOWS.get(normalized)
    if named is not None:
        return TimeWindow(*named)

    match = TIME_WINDOW_PATTERN.fullmatch(normalized)
    if match is None:
        raise SchedulingValidationError(
            "preferred_time_window must be morning, afternoon, evening, or HH:MM-HH:MM."
        )
    start = time(
        int(match.group("start_hour")),
        int(match.group("start_minute")),
    )
    end = time(
        int(match.group("end_hour")),
        int(match.group("end_minute")),
    )
    if end <= start:
        raise SchedulingValidationError(
            "preferred_time_window must end after it starts."
        )
    return TimeWindow(start, end)


def query_freebusy(
    client: GoogleCalendarClient,
    *,
    calendar_ids: list[str],
    time_min: datetime,
    time_max: datetime,
    timezone: str,
) -> dict[str, list[BusyPeriod]]:
    """Query independent busy periods for up to 50 calendars."""
    _require_aware(time_min, "time_min")
    _require_aware(time_max, "time_max")
    if time_max <= time_min:
        raise SchedulingValidationError("time_max must be after time_min.")
    if len(calendar_ids) > GOOGLE_FREEBUSY_CALENDAR_LIMIT:
        raise SchedulingValidationError(
            "A FreeBusy request supports at most 50 calendars."
        )

    response = (
        client.freebusy()
        .query(
            body={
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "timeZone": timezone,
                "items": [{"id": calendar_id} for calendar_id in calendar_ids],
            }
        )
        .execute()
    )
    calendars = response.get("calendars", {})
    result: dict[str, list[BusyPeriod]] = {}
    for calendar_id in calendar_ids:
        values = calendars.get(calendar_id)
        if values is None or values.get("errors"):
            raise SchedulingProviderError(
                f"FreeBusy data is unavailable for calendar {calendar_id!r}."
            )
        result[calendar_id] = [
            BusyPeriod(
                start=datetime.fromisoformat(item["start"].replace("Z", "+00:00")),
                end=datetime.fromisoformat(item["end"].replace("Z", "+00:00")),
            )
            for item in values.get("busy", [])
        ]
    return result


def get_busy_ranges(
    client: GoogleCalendarClient,
    *,
    workers: list[Worker],
    time_min: datetime,
    time_max: datetime,
    timezone: str,
) -> dict[uuid.UUID, list[TimeRange]]:
    """Fetch and map Google FreeBusy ranges for candidate workers."""
    workers_by_calendar: dict[str, Worker] = {}
    for worker in workers:
        if not worker.calendar_id:
            raise WorkerCalendarError(
                f"Worker {worker.id} does not have a linked calendar."
            )
        workers_by_calendar[worker.calendar_id] = worker

    busy_by_worker: dict[uuid.UUID, list[TimeRange]] = {
        worker.id: [] for worker in workers
    }
    calendar_ids = list(workers_by_calendar)
    for calendar_chunk in _chunks(
        calendar_ids,
        GOOGLE_FREEBUSY_CALENDAR_LIMIT,
    ):
        response = query_freebusy(
            client,
            calendar_ids=calendar_chunk,
            time_min=time_min,
            time_max=time_max,
            timezone=timezone,
        )
        for calendar_id, busy_periods in response.items():
            worker = workers_by_calendar[calendar_id]
            busy_by_worker[worker.id].extend(
                period.as_range() for period in busy_periods
            )
    return {
        worker_id: _merge_ranges(ranges) for worker_id, ranges in busy_by_worker.items()
    }


def build_working_ranges(
    worker: Worker,
    *,
    start_date: date,
    days_ahead: int,
    timezone: str,
    not_before: datetime | None = None,
) -> list[TimeRange]:
    """Build canonical UTC ranges from a worker's local weekly schedule."""
    if days_ahead <= 0:
        raise SchedulingValidationError("days_ahead must be positive.")
    zone = ZoneInfo(timezone)
    lower_bound = _as_utc(not_before) if not_before is not None else None
    ranges: list[TimeRange] = []

    for day_offset in range(days_ahead):
        current_date = start_date + timedelta(days=day_offset)
        weekday = WEEKDAY_NAMES[current_date.weekday()]
        day_ranges = worker.working_hours_json.get(weekday, [])
        if not isinstance(day_ranges, list):
            raise SchedulingValidationError(
                f"working_hours_json[{weekday!r}] must be a list."
            )
        for raw_range in day_ranges:
            if not isinstance(raw_range, dict):
                raise SchedulingValidationError(
                    "Each working-hours range must be an object."
                )
            try:
                start_clock, start_offset = _parse_clock(str(raw_range["start"]))
                end_clock, end_offset = _parse_clock(
                    str(raw_range["end"]),
                    allow_24=True,
                )
            except KeyError as exc:
                raise SchedulingValidationError(
                    "Working-hours ranges require start and end."
                ) from exc

            local_start = _localize_wall_time(
                current_date,
                start_clock,
                zone,
                day_offset=start_offset,
            )
            local_end = _localize_wall_time(
                current_date,
                end_clock,
                zone,
                day_offset=end_offset,
                prefer_late_fold=True,
            )
            start_utc = local_start.astimezone(UTC)
            end_utc = local_end.astimezone(UTC)
            if end_utc <= start_utc:
                raise SchedulingValidationError(
                    f"Invalid working range {raw_range!r} for {weekday}."
                )
            if lower_bound is not None:
                start_utc = max(start_utc, lower_bound)
            if end_utc > start_utc:
                ranges.append(TimeRange(start_utc, end_utc))

    return _merge_ranges(ranges)


def subtract_busy_ranges(
    working_ranges: list[TimeRange],
    busy_ranges: list[TimeRange],
) -> list[TimeRange]:
    """Subtract busy half-open intervals from working intervals."""
    working = _merge_ranges(working_ranges)
    busy = _merge_ranges(busy_ranges)
    available: list[TimeRange] = []

    for working_range in working:
        cursor = working_range.start
        for busy_range in busy:
            if busy_range.end <= cursor:
                continue
            if busy_range.start >= working_range.end:
                break
            if busy_range.start > cursor:
                available.append(
                    TimeRange(cursor, min(busy_range.start, working_range.end))
                )
            cursor = max(cursor, busy_range.end)
            if cursor >= working_range.end:
                break
        if cursor < working_range.end:
            available.append(TimeRange(cursor, working_range.end))
    return available


def _ceil_to_slot_grid(value: datetime) -> datetime:
    """Round a UTC datetime up to the next 15-minute boundary."""
    normalized = _as_utc(value).replace(second=0, microsecond=0)
    remainder = normalized.minute % SLOT_INTERVAL_MINUTES
    if remainder:
        normalized += timedelta(minutes=SLOT_INTERVAL_MINUTES - remainder)
    return normalized


def generate_candidate_slots(
    worker: Worker,
    *,
    available_ranges: list[TimeRange],
    duration_minutes: int,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
    timezone: str,
) -> list[ProposedSlot]:
    """Generate real appointment slots fully contained in free ranges."""
    if not worker.calendar_id:
        raise WorkerCalendarError(
            f"Worker {worker.id} does not have a linked calendar."
        )
    if duration_minutes <= 0:
        raise SchedulingValidationError("duration_minutes must be positive.")
    if buffer_before_minutes < 0 or buffer_after_minutes < 0:
        raise SchedulingValidationError("Buffers cannot be negative.")

    duration = timedelta(minutes=duration_minutes)
    before = timedelta(minutes=buffer_before_minutes)
    after = timedelta(minutes=buffer_after_minutes)
    step = timedelta(minutes=SLOT_INTERVAL_MINUTES)
    zone = ZoneInfo(timezone)
    slots: list[ProposedSlot] = []

    for free_range in _merge_ranges(available_ranges):
        appointment_start = _ceil_to_slot_grid(free_range.start + before)
        while appointment_start + duration + after <= free_range.end:
            appointment_end = appointment_start + duration
            slots.append(
                ProposedSlot(
                    worker_id=worker.id,
                    worker_name=worker.name,
                    calendar_id=worker.calendar_id,
                    start_at=appointment_start.astimezone(zone),
                    end_at=appointment_end.astimezone(zone),
                    blocked_start_at=(appointment_start - before).astimezone(zone),
                    blocked_end_at=(appointment_end + after).astimezone(zone),
                )
            )
            appointment_start += step
    return slots


def _window_penalty_minutes(
    slot: ProposedSlot,
    preferred_window: TimeWindow | None,
) -> int:
    """Return zero inside the window and distance to it otherwise."""
    if preferred_window is None:
        return 0
    slot_minutes = slot.start_at.hour * 60 + slot.start_at.minute
    start_minutes = preferred_window.start.hour * 60 + preferred_window.start.minute
    end_minutes = preferred_window.end.hour * 60 + preferred_window.end.minute
    if start_minutes <= slot_minutes < end_minutes:
        return 0
    if slot_minutes < start_minutes:
        return start_minutes - slot_minutes
    return slot_minutes - end_minutes + 1


def _slot_score(
    slot: ProposedSlot,
    *,
    preferred_date: date,
    preferred_window: TimeWindow | None,
) -> tuple[int, int, datetime, str]:
    """Rank slots by date proximity, window proximity, then chronology."""
    return (
        abs((slot.start_at.date() - preferred_date).days),
        _window_penalty_minutes(slot, preferred_window),
        slot.start_at,
        slot.worker_name.casefold(),
    )


def propose_slots(
    session: Session,
    client: GoogleCalendarClient,
    *,
    clinic_id: uuid.UUID,
    service_id: uuid.UUID | None = None,
    duration_minutes: int | None = None,
    worker_id: uuid.UUID | None = None,
    preferred_date: date | None = None,
    preferred_time_window: str | None = None,
    days_ahead: int = 14,
    max_slots: int = 3,
    now: datetime | None = None,
) -> list[ProposedSlot]:
    """Return up to `max_slots` real FreeBusy-backed appointment options."""
    if days_ahead <= 0:
        raise SchedulingValidationError("days_ahead must be positive.")
    if max_slots <= 0:
        raise SchedulingValidationError("max_slots must be positive.")
    if (service_id is None) == (duration_minutes is None):
        raise SchedulingValidationError(
            "Provide exactly one of service_id or duration_minutes."
        )

    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise SchedulingValidationError("Clinic does not exist.")

    buffer_before = 0
    buffer_after = 0
    service: Service | None = None
    if service_id is not None:
        service = session.get(Service, service_id)
        if (
            service is None
            or service.clinic_id != clinic_id
            or not service.is_active
            or not service.is_bookable_by_bot
        ):
            raise SchedulingValidationError("Service does not exist or is inactive.")
        duration = service.duration_minutes
        buffer_before = service.buffer_before_minutes
        buffer_after = service.buffer_after_minutes
    else:
        if duration_minutes is None or duration_minutes <= 0:
            raise SchedulingValidationError("duration_minutes must be positive.")
        duration = duration_minutes

    query = select(Worker).where(
        Worker.clinic_id == clinic_id,
        Worker.is_active.is_(True),
        Worker.calendar_id.is_not(None),
    )
    if worker_id is not None:
        query = query.where(Worker.id == worker_id)
    workers = list(session.scalars(query.order_by(Worker.name, Worker.id)))
    if service is not None and service.allowed_worker_ids is not None:
        allowed_worker_ids = {uuid.UUID(value) for value in service.allowed_worker_ids}
        workers = [worker for worker in workers if worker.id in allowed_worker_ids]
    if not workers:
        return []

    current = now or datetime.now(UTC)
    current_utc = _as_utc(current)
    zone = ZoneInfo(clinic.timezone)
    today = current_utc.astimezone(zone).date()
    target_date = preferred_date or today
    if target_date < today:
        raise SchedulingValidationError("preferred_date cannot be in the past.")
    preferred_window = _parse_time_window(preferred_time_window)

    working_by_worker = {
        worker.id: build_working_ranges(
            worker,
            start_date=target_date,
            days_ahead=days_ahead,
            timezone=clinic.timezone,
            not_before=current_utc,
        )
        for worker in workers
    }
    all_working_ranges = [
        item for ranges in working_by_worker.values() for item in ranges
    ]
    if not all_working_ranges:
        return []

    time_min = min(item.start for item in all_working_ranges)
    time_max = max(item.end for item in all_working_ranges)
    busy_by_worker = get_busy_ranges(
        client,
        workers=workers,
        time_min=time_min,
        time_max=time_max,
        timezone=clinic.timezone,
    )

    candidates: list[ProposedSlot] = []
    for worker in workers:
        available = subtract_busy_ranges(
            working_by_worker[worker.id],
            busy_by_worker[worker.id],
        )
        candidates.extend(
            generate_candidate_slots(
                worker,
                available_ranges=available,
                duration_minutes=duration,
                buffer_before_minutes=buffer_before,
                buffer_after_minutes=buffer_after,
                timezone=clinic.timezone,
            )
        )

    candidates.sort(
        key=lambda slot: _slot_score(
            slot,
            preferred_date=target_date,
            preferred_window=preferred_window,
        )
    )
    return candidates[:max_slots]


def check_slot_available(
    client: GoogleCalendarClient,
    *,
    worker: Worker,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
) -> bool:
    """Double-check working hours and Google availability before booking."""
    _require_aware(start_at, "start_at")
    _require_aware(end_at, "end_at")
    if end_at <= start_at:
        raise SchedulingValidationError("end_at must be after start_at.")
    if buffer_before_minutes < 0 or buffer_after_minutes < 0:
        raise SchedulingValidationError("Buffers cannot be negative.")
    if not worker.calendar_id:
        raise WorkerCalendarError(
            f"Worker {worker.id} does not have a linked calendar."
        )

    blocked = TimeRange(
        _as_utc(start_at) - timedelta(minutes=buffer_before_minutes),
        _as_utc(end_at) + timedelta(minutes=buffer_after_minutes),
    )
    zone = ZoneInfo(timezone)
    local_start_date = blocked.start.astimezone(zone).date()
    local_end_date = blocked.end.astimezone(zone).date()
    working_ranges = build_working_ranges(
        worker,
        start_date=local_start_date,
        days_ahead=(local_end_date - local_start_date).days + 1,
        timezone=timezone,
    )
    if not any(
        working.start <= blocked.start and blocked.end <= working.end
        for working in working_ranges
    ):
        return False

    busy = get_busy_ranges(
        client,
        workers=[worker],
        time_min=blocked.start,
        time_max=blocked.end,
        timezone=timezone,
    )[worker.id]
    return not any(
        occupied.start < blocked.end and blocked.start < occupied.end
        for occupied in busy
    )


def build_worker_event_body(
    *,
    worker: Worker,
    summary: str,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    description: str | None = None,
    source: AppointmentSource | str = AppointmentSource.VOICE_BOT,
    call_id: uuid.UUID | str | None = None,
    appointment_id: uuid.UUID | str | None = None,
    call_session_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Build an event payload with worker and call traceability metadata."""
    _require_aware(start_at, "start_at")
    _require_aware(end_at, "end_at")
    private_properties = {
        "worker_id": str(worker.id),
        "source": str(source),
    }
    if call_id is not None:
        private_properties["call_id"] = str(call_id)
    if appointment_id is not None:
        private_properties["appointment_id"] = str(appointment_id)
    if call_session_id is not None:
        private_properties["call_session_id"] = str(call_session_id)

    event: dict[str, Any] = {
        "summary": summary,
        "start": {
            "dateTime": start_at.isoformat(),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_at.isoformat(),
            "timeZone": timezone,
        },
        "extendedProperties": {"private": private_properties},
    }
    if description:
        event["description"] = description
    if worker.color_id:
        event["colorId"] = worker.color_id
    return event


def insert_worker_event(
    client: GoogleCalendarClient,
    *,
    worker: Worker,
    event_body: dict[str, Any],
) -> dict[str, Any]:
    """Insert an event into the worker's dedicated calendar."""
    if not worker.calendar_id:
        raise WorkerCalendarError("Worker does not have a linked calendar.")
    return (
        client.events()
        .insert(
            calendarId=worker.calendar_id,
            body=event_body,
        )
        .execute()
    )
