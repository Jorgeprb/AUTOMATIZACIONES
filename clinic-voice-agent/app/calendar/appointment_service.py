"""Transactional appointment operations used by internal agent tools."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.calendar.event_templates import (
    DEFAULT_CALENDAR_EVENT_DESCRIPTION_TEMPLATE,
    DEFAULT_CALENDAR_EVENT_TITLE_TEMPLATE,
    calendar_template_values,
    render_calendar_event_template,
)
from app.calendar.google_client import GoogleCalendarClient
from app.calendar.scheduler import (
    SchedulingError,
    build_worker_event_body,
    check_slot_available,
    insert_worker_event,
)
from app.models import (
    Appointment,
    AssistantConfig,
    AppointmentSource,
    AppointmentStatus,
    CallSession,
    Clinic,
    Service,
    Worker,
    IntegrationOutbox,
    ClinicCustomer,
    ClinicResource,
    ResourceReservation,
    ServiceResourceRequirement,
)
from app.customer_service import normalize_customer_phone

from app.utils.phone import normalize_phone

logger = logging.getLogger(__name__)


class AgentAppointmentError(RuntimeError):
    """Base exception for internal appointment operations."""


class AgentResourceNotFound(AgentAppointmentError):
    """Raised when a requested clinic resource does not exist."""


class AppointmentUnavailable(AgentAppointmentError):
    """Raised when a slot cannot be safely booked."""


class CalendarOperationFailed(AgentAppointmentError):
    """Raised when Google Calendar rejects an operation."""


class AppointmentPersistenceFailed(AgentAppointmentError):
    """Raised when PostgreSQL cannot persist a Google-side change."""


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    """Result of checking an exact slot."""

    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceTiming:
    """Duration and buffers applied to one appointment."""

    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int


def _reset_request_transaction(session: Session) -> None:
    """Finish read-only credential work before acquiring booking locks."""
    if session.in_transaction():
        session.commit()


def _get_clinic(session: Session, clinic_id: uuid.UUID) -> Clinic:
    """Return a clinic or raise a domain error."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise AgentResourceNotFound("Clinic not found.")
    return clinic


def _get_service_timing(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    service_id: uuid.UUID | None,
    start_at: datetime,
    end_at: datetime,
) -> ServiceTiming:
    """Resolve service buffers and validate the requested duration."""
    actual_minutes = int((end_at - start_at).total_seconds() // 60)
    if actual_minutes <= 0:
        raise AppointmentUnavailable("Appointment duration must be positive.")
    if service_id is None:
        return ServiceTiming(actual_minutes, 0, 0)

    service = session.get(Service, service_id)
    if service is None or service.clinic_id != clinic_id or not service.is_active:
        raise AgentResourceNotFound("Service not found or inactive.")
    if end_at - start_at != timedelta(minutes=service.duration_minutes):
        raise AppointmentUnavailable(
            "Requested interval does not match the service duration."
        )
    return ServiceTiming(
        service.duration_minutes,
        service.buffer_before_minutes,
        service.buffer_after_minutes,
    )


def _appointment_blocked_range(
    appointment: Appointment,
) -> tuple[datetime, datetime]:
    """Expand an existing appointment by its service buffers."""
    before = appointment.service.buffer_before_minutes if appointment.service else 0
    after = appointment.service.buffer_after_minutes if appointment.service else 0
    return (
        appointment.start_at - timedelta(minutes=before),
        appointment.end_at + timedelta(minutes=after),
    )


def _has_local_overlap(
    session: Session,
    *,
    worker_id: uuid.UUID,
    blocked_start: datetime,
    blocked_end: datetime,
    exclude_appointment_id: uuid.UUID | None = None,
) -> bool:
    """Check active PostgreSQL appointments, including service buffers."""
    query = (
        select(Appointment)
        .options(joinedload(Appointment.service))
        .where(
            Appointment.worker_id == worker_id,
            Appointment.status.in_(
                (
                    AppointmentStatus.PENDING,
                    AppointmentStatus.CONFIRMED,
                )
            ),
        )
    )
    if exclude_appointment_id is not None:
        query = query.where(Appointment.id != exclude_appointment_id)

    for existing in session.scalars(query):
        existing_start, existing_end = _appointment_blocked_range(existing)
        if existing_start < blocked_end and blocked_start < existing_end:
            return True
    return False


def check_exact_availability(
    session: Session,
    client: GoogleCalendarClient,
    *,
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    service_id: uuid.UUID | None = None,
) -> AvailabilityResult:
    """Check local state, working hours, and Google for one exact slot."""
    clinic = _get_clinic(session, clinic_id)
    worker = session.get(Worker, worker_id)
    if (
        worker is None
        or worker.clinic_id != clinic_id
        or not worker.is_active
        or not worker.calendar_id
    ):
        raise AgentResourceNotFound(
            "Worker not found, inactive, or missing a calendar."
        )
    timing = _get_service_timing(
        session,
        clinic_id=clinic_id,
        service_id=service_id,
        start_at=start_at,
        end_at=end_at,
    )
    blocked_start = start_at.astimezone(UTC) - timedelta(
        minutes=timing.buffer_before_minutes
    )
    blocked_end = end_at.astimezone(UTC) + timedelta(
        minutes=timing.buffer_after_minutes
    )
    if _has_local_overlap(
        session,
        worker_id=worker.id,
        blocked_start=blocked_start,
        blocked_end=blocked_end,
    ):
        return AvailabilityResult(
            available=False,
            reason="The slot overlaps an existing appointment.",
        )
    try:
        _lock_and_validate_resources(
            session,
            clinic_id=clinic_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
            timezone=clinic.timezone,
            lock=False,
        )
    except AppointmentUnavailable as exc:
        return AvailabilityResult(available=False, reason=str(exc))
    try:
        available = check_slot_available(
            client,
            worker=worker,
            start_at=start_at,
            end_at=end_at,
            timezone=clinic.timezone,
            buffer_before_minutes=timing.buffer_before_minutes,
            buffer_after_minutes=timing.buffer_after_minutes,
        )
    except SchedulingError as exc:
        raise CalendarOperationFailed(str(exc)) from exc
    return AvailabilityResult(
        available=available,
        reason=None if available else "The slot is busy or outside working hours.",
    )




def _resource_schedule_allows(resource: ClinicResource, *, start_at: datetime, end_at: datetime, timezone: str) -> bool:
    """Check optional weekly resource hours using the same half-open semantics."""
    schedule = resource.schedule_json or {}
    if not schedule:
        return True
    local_start = start_at.astimezone(ZoneInfo(timezone))
    local_end = end_at.astimezone(ZoneInfo(timezone))
    if local_start.date() != local_end.date():
        return False
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[local_start.weekday()]
    ranges = schedule.get(weekday, [])
    for item in ranges if isinstance(ranges, list) else []:
        try:
            start_h, start_m = map(int, str(item["start"]).split(":", 1))
            end_h, end_m = map(int, str(item["end"]).split(":", 1))
        except (KeyError, ValueError, TypeError):
            continue
        range_start = local_start.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        range_end = local_start.replace(hour=end_h % 24, minute=end_m, second=0, microsecond=0)
        if end_h == 24:
            range_end += timedelta(days=1)
        if range_start <= local_start and local_end <= range_end:
            return True
    return False


def _lock_and_validate_resources(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    service_id: uuid.UUID | None,
    start_at: datetime,
    end_at: datetime,
    timezone: str,
    lock: bool,
) -> list[tuple[ClinicResource, int]]:
    if service_id is None:
        return []
    requirements = list(session.scalars(select(ServiceResourceRequirement).where(ServiceResourceRequirement.clinic_id == clinic_id, ServiceResourceRequirement.service_id == service_id)))
    resolved: list[tuple[ClinicResource, int]] = []
    for requirement in requirements:
        query = select(ClinicResource).where(ClinicResource.id == requirement.resource_id, ClinicResource.clinic_id == clinic_id, ClinicResource.is_active.is_(True))
        if lock:
            query = query.with_for_update()
        resource = session.scalar(query)
        if resource is None or requirement.quantity > resource.capacity:
            raise AppointmentUnavailable("A required resource is unavailable.")
        if not _resource_schedule_allows(resource, start_at=start_at, end_at=end_at, timezone=timezone):
            raise AppointmentUnavailable("A required resource is outside its working hours.")
        used = session.scalar(select(func.coalesce(func.sum(ResourceReservation.quantity), 0)).where(ResourceReservation.resource_id == resource.id, ResourceReservation.start_at < end_at.astimezone(UTC), ResourceReservation.end_at > start_at.astimezone(UTC))) or 0
        if int(used) + requirement.quantity > resource.capacity:
            raise AppointmentUnavailable("A required resource has no remaining capacity.")
        resolved.append((resource, requirement.quantity))
    return resolved


def _upsert_customer_after_booking(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    name: str,
    phone: str,
    worker_id: uuid.UUID,
    call_session: CallSession | None,
    config: AssistantConfig | None,
) -> ClinicCustomer | None:
    if config is not None and not config.remember_customer_after_booking:
        return None
    try:
        normalized = normalize_customer_phone(phone)
    except ValueError:
        return None
    customer = session.scalar(select(ClinicCustomer).where(ClinicCustomer.clinic_id == clinic_id, ClinicCustomer.normalized_phone == normalized))
    now = datetime.now(UTC)
    if customer is None:
        customer = ClinicCustomer(clinic_id=clinic_id, name=name.strip(), normalized_phone=normalized, display_phone=phone.strip(), personalization_enabled=True, is_active=True, first_contact_at=now, last_contact_at=now, preferred_worker_id=worker_id)
        session.add(customer)
        session.flush()
    else:
        # Do not replace a useful known name with a short or uncertain transcript.
        if len(name.strip()) >= 3 and (not customer.name or customer.name == "Cliente"):
            customer.name = name.strip()
        customer.display_phone = phone.strip()
        customer.last_contact_at = now
        if customer.preferred_worker_id is None or (config and config.suggest_preferred_worker_enabled):
            customer.preferred_worker_id = worker_id
        customer.is_active = True
    if call_session is not None:
        call_session.customer_id = customer.id
        if not call_session.caller_name:
            call_session.caller_name = customer.name
    return customer


def _compensate_google_event(
    client: GoogleCalendarClient,
    *,
    calendar_id: str,
    event_id: str,
) -> bool:
    """Best-effort deletion after PostgreSQL fails; report success."""
    try:
        client.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates="none",
        ).execute()
        return True
    except Exception:
        logger.exception(
            "google_event_compensation_failed",
            extra={
                "calendar_id": calendar_id,
                "google_event_id": event_id,
            },
        )
        return False


def _enqueue_google_delete_compensation(
    session: Session, *, clinic_id: uuid.UUID, calendar_id: str, event_id: str
) -> None:
    """Persist a retryable compensation command without duplicating work."""
    dedupe_key = f"google-delete:{calendar_id}:{event_id}"
    existing = session.scalar(
        select(IntegrationOutbox).where(IntegrationOutbox.dedupe_key == dedupe_key)
    )
    if existing is None:
        session.add(
            IntegrationOutbox(
                kind="google_calendar.delete_event",
                dedupe_key=dedupe_key,
                payload_json={
                    "clinic_id": str(clinic_id),
                    "calendar_id": calendar_id,
                    "event_id": event_id,
                },
            )
        )
        session.commit()


def create_appointment_transactional(
    session: Session,
    client: GoogleCalendarClient,
    *,
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    service_id: uuid.UUID | None,
    patient_name: str,
    patient_phone: str,
    reason: str | None,
    start_at: datetime,
    end_at: datetime,
    call_session_id: uuid.UUID | None,
    idempotency_key: str | None = None,
) -> Appointment:
    """Lock, recheck, create in Google, and persist one appointment."""
    normalized_phone = normalize_phone(patient_phone)
    normalized_idempotency = (idempotency_key or "").strip()[:200] or None
    if normalized_idempotency:
        existing = session.scalar(
            select(Appointment)
            .options(joinedload(Appointment.worker), joinedload(Appointment.service))
            .where(
                Appointment.clinic_id == clinic_id,
                Appointment.idempotency_key == normalized_idempotency,
            )
        )
        if existing is not None:
            logger.info(
                "appointment_idempotency_hit",
                extra={"appointment_id": str(existing.id), "clinic_id": str(clinic_id)},
            )
            return existing
    _reset_request_transaction(session)
    appointment_id = uuid.uuid4()
    google_calendar_id: str | None = None
    google_event_id: str | None = None
    google_event_created = False

    session.begin()
    try:
        clinic = session.get(Clinic, clinic_id)
        if clinic is None:
            raise AgentResourceNotFound("Clinic not found.")
        worker = session.scalar(
            select(Worker)
            .where(
                Worker.id == worker_id,
                Worker.clinic_id == clinic_id,
                Worker.is_active.is_(True),
            )
            .with_for_update()
        )
        if worker is None or not worker.calendar_id:
            raise AgentResourceNotFound(
                "Worker not found, inactive, or missing a calendar."
            )
        timing = _get_service_timing(
            session,
            clinic_id=clinic_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
        )
        call_session: CallSession | None = None
        assistant_config: AssistantConfig | None = None
        if call_session_id is not None:
            call_session = session.get(CallSession, call_session_id)
            if call_session is None or (
                call_session.clinic_id is not None
                and call_session.clinic_id != clinic_id
            ):
                raise AgentResourceNotFound(
                    "Call session not found or belongs to another clinic."
                )
            if call_session.assistant_config_id is not None:
                assistant_config = session.get(
                    AssistantConfig,
                    call_session.assistant_config_id,
                )
        if assistant_config is None:
            assistant_config = session.scalar(
                select(AssistantConfig).where(
                    AssistantConfig.clinic_id == clinic_id,
                    AssistantConfig.is_active.is_(True),
                )
            )

        blocked_start = start_at.astimezone(UTC) - timedelta(
            minutes=timing.buffer_before_minutes
        )
        blocked_end = end_at.astimezone(UTC) + timedelta(
            minutes=timing.buffer_after_minutes
        )
        if _has_local_overlap(
            session,
            worker_id=worker.id,
            blocked_start=blocked_start,
            blocked_end=blocked_end,
        ):
            raise AppointmentUnavailable("The slot was booked by another appointment.")
        reserved_resources = _lock_and_validate_resources(
            session,
            clinic_id=clinic_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
            timezone=clinic.timezone,
            lock=True,
        )
        try:
            google_available = check_slot_available(
                client,
                worker=worker,
                start_at=start_at,
                end_at=end_at,
                timezone=clinic.timezone,
                buffer_before_minutes=timing.buffer_before_minutes,
                buffer_after_minutes=timing.buffer_after_minutes,
            )
        except SchedulingError as exc:
            raise CalendarOperationFailed(str(exc)) from exc
        if not google_available:
            raise AppointmentUnavailable("The slot is no longer available.")

        service = session.get(Service, service_id) if service_id is not None else None
        zone = ZoneInfo(clinic.timezone)
        local_start = start_at.astimezone(zone)
        local_end = end_at.astimezone(zone)
        template_values = calendar_template_values(
            appointment_id=appointment_id,
            call_session_id=call_session_id,
            clinic_name=clinic.name,
            patient_name=patient_name,
            patient_phone=normalized_phone,
            reason=reason,
            service_name=(service.public_name or service.name) if service else None,
            worker_name=worker.name,
            start_at=local_start,
            end_at=local_end,
        )
        title_template = (
            assistant_config.calendar_event_title_template
            if assistant_config is not None
            else DEFAULT_CALENDAR_EVENT_TITLE_TEMPLATE
        )
        description_template = (
            assistant_config.calendar_event_description_template
            if assistant_config is not None
            else DEFAULT_CALENDAR_EVENT_DESCRIPTION_TEMPLATE
        )
        summary = render_calendar_event_template(
            title_template,
            template_values,
            label="title",
        )
        description = render_calendar_event_template(
            description_template,
            template_values,
            label="description",
        )
        event_body = build_worker_event_body(
            worker=worker,
            summary=summary,
            description=description or None,
            start_at=start_at,
            end_at=end_at,
            timezone=clinic.timezone,
            source=AppointmentSource.VOICE_BOT,
            appointment_id=appointment_id,
            call_session_id=call_session_id,
        )
        google_calendar_id = worker.calendar_id
        google_event_id = appointment_id.hex
        event_body["id"] = google_event_id
        try:
            google_event = insert_worker_event(
                client,
                worker=worker,
                event_body=event_body,
            )
            google_event_created = True
            google_event_id = str(google_event.get("id", google_event_id))
        except Exception as exc:
            _compensate_google_event(
                client,
                calendar_id=google_calendar_id,
                event_id=google_event_id,
            )
            raise CalendarOperationFailed(
                "Google Calendar could not create the event."
            ) from exc

        customer = _upsert_customer_after_booking(
            session,
            clinic_id=clinic_id,
            name=patient_name,
            phone=normalized_phone,
            worker_id=worker.id,
            call_session=call_session,
            config=assistant_config,
        )
        appointment = Appointment(
            id=appointment_id,
            clinic_id=clinic_id,
            worker_id=worker.id,
            service_id=service_id,
            google_calendar_id=google_calendar_id,
            google_event_id=google_event_id,
            patient_name=patient_name,
            patient_phone=normalized_phone,
            idempotency_key=normalized_idempotency,
            reason=reason,
            start_at=start_at,
            end_at=end_at,
            status=AppointmentStatus.CONFIRMED,
            source=AppointmentSource.VOICE_BOT,
            call_session_id=call_session_id,
            customer_id=(customer.id if customer is not None else None),
        )
        session.add(appointment)
        session.flush()
        for resource, quantity in reserved_resources:
            session.add(
                ResourceReservation(
                    clinic_id=clinic_id,
                    appointment_id=appointment.id,
                    resource_id=resource.id,
                    quantity=quantity,
                    start_at=start_at.astimezone(UTC),
                    end_at=end_at.astimezone(UTC),
                )
            )
        session.commit()
        return appointment
    except (
        AgentResourceNotFound,
        AppointmentUnavailable,
        CalendarOperationFailed,
    ):
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        if google_event_created and google_calendar_id and google_event_id:
            compensated = _compensate_google_event(
                client,
                calendar_id=google_calendar_id,
                event_id=google_event_id,
            )
            if not compensated:
                _enqueue_google_delete_compensation(
                    session,
                    clinic_id=clinic_id,
                    calendar_id=google_calendar_id,
                    event_id=google_event_id,
                )
        raise AppointmentPersistenceFailed(
            "Appointment could not be persisted."
        ) from exc


def _find_appointment_for_cancellation(
    session: Session,
    *,
    clinic: Clinic,
    appointment_id: uuid.UUID | None,
    patient_phone: str | None,
    approximate_date: date | None,
) -> Appointment | None:
    """Lock an appointment by ID or the nearest phone/date match."""
    if appointment_id is not None:
        return session.scalar(
            select(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.clinic_id == clinic.id,
            )
            .with_for_update()
        )

    if patient_phone is None or approximate_date is None:
        return None
    zone = ZoneInfo(clinic.timezone)
    range_start = datetime.combine(
        approximate_date - timedelta(days=1),
        time.min,
        zone,
    ).astimezone(UTC)
    range_end = datetime.combine(
        approximate_date + timedelta(days=2),
        time.min,
        zone,
    ).astimezone(UTC)
    candidates = list(
        session.scalars(
            select(Appointment)
            .where(
                Appointment.clinic_id == clinic.id,
                Appointment.patient_phone == patient_phone,
                Appointment.start_at >= range_start,
                Appointment.start_at < range_end,
                Appointment.status.in_(
                    (
                        AppointmentStatus.PENDING,
                        AppointmentStatus.CONFIRMED,
                        AppointmentStatus.CANCELLED,
                    )
                ),
            )
            .with_for_update()
        )
    )
    target = datetime.combine(
        approximate_date,
        time(12, 0),
        zone,
    ).astimezone(UTC)
    return min(
        candidates,
        key=lambda item: abs(item.start_at.astimezone(UTC) - target),
        default=None,
    )


def cancel_appointment_transactional(
    session: Session,
    client: GoogleCalendarClient,
    *,
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID | None,
    patient_phone: str | None,
    approximate_date: date | None,
) -> tuple[Appointment, bool]:
    """Delete the Google event and soft-cancel the local appointment."""
    patient_phone = normalize_phone(patient_phone) if patient_phone else None
    _reset_request_transaction(session)
    session.begin()
    try:
        clinic = session.get(Clinic, clinic_id)
        if clinic is None:
            raise AgentResourceNotFound("Clinic not found.")
        appointment = _find_appointment_for_cancellation(
            session,
            clinic=clinic,
            appointment_id=appointment_id,
            patient_phone=patient_phone,
            approximate_date=approximate_date,
        )
        if appointment is None:
            raise AgentResourceNotFound("Appointment not found.")
        if appointment.status is AppointmentStatus.CANCELLED:
            session.commit()
            return appointment, True

        try:
            client.events().delete(
                calendarId=appointment.google_calendar_id,
                eventId=appointment.google_event_id,
                sendUpdates="none",
            ).execute()
        except Exception as exc:
            raise CalendarOperationFailed(
                "Google Calendar could not cancel the event."
            ) from exc

        appointment.status = AppointmentStatus.CANCELLED
        session.flush()
        session.commit()
        return appointment, False
    except (
        AgentResourceNotFound,
        CalendarOperationFailed,
    ):
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise AppointmentPersistenceFailed(
            "Cancellation could not be persisted."
        ) from exc
