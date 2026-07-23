"""Internal endpoints called by voice-agent tools."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar.appointment_service import (
    AgentAppointmentError,
    AgentResourceNotFound,
    AppointmentPersistenceFailed,
    AppointmentUnavailable,
    CalendarOperationFailed,
    cancel_appointment_transactional,
    check_exact_availability,
    create_appointment_transactional,
)
from app.calendar.google_client import (
    GoogleAuthorizationRequired,
    get_authorized_calendar_client,
)
from app.calendar.scheduler import (
    SchedulingError,
    SchedulingProviderError,
    propose_slots,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Clinic, Service, Worker
from app.schemas import (
    AgentAppointmentConfirmation,
    AgentAvailabilityRequest,
    AgentAvailabilityResponse,
    AgentCancelAppointmentRequest,
    AgentCancellationConfirmation,
    AgentClinicInfoRequest,
    AgentClinicInfoResponse,
    AgentCreateAppointmentRequest,
    AgentProposeSlotsRequest,
    AgentProposeSlotsResponse,
    AgentServiceInfo,
    AgentSlotResponse,
    AgentWorkerInfo,
)

router = APIRouter(prefix="/agent", tags=["agent-tools"])


def _raise_http_error(exc: Exception) -> NoReturn:
    """Map domain and integration failures to stable HTTP responses."""
    if isinstance(exc, AgentResourceNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AppointmentUnavailable):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, GoogleAuthorizationRequired):
        code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, (CalendarOperationFailed, SchedulingProviderError)):
        code = status.HTTP_502_BAD_GATEWAY
    elif isinstance(exc, AppointmentPersistenceFailed):
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post(
    "/check_availability",
    response_model=AgentAvailabilityResponse,
)
def check_availability(
    payload: AgentAvailabilityRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentAvailabilityResponse:
    """Recheck one exact worker slot against PostgreSQL and Google."""
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            payload.clinic_id,
        )
        result = check_exact_availability(
            session,
            client,
            clinic_id=payload.clinic_id,
            worker_id=payload.worker_id,
            service_id=payload.service_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
    except (
        AgentAppointmentError,
        GoogleAuthorizationRequired,
    ) as exc:
        _raise_http_error(exc)
    return AgentAvailabilityResponse(
        available=result.available,
        clinic_id=payload.clinic_id,
        worker_id=payload.worker_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        reason=result.reason,
    )


@router.post("/propose_slots", response_model=AgentProposeSlotsResponse)
def propose_agent_slots(
    payload: AgentProposeSlotsRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentProposeSlotsResponse:
    """Return ranked FreeBusy-backed appointment alternatives."""
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            payload.clinic_id,
        )
        slots = propose_slots(
            session,
            client,
            clinic_id=payload.clinic_id,
            service_id=payload.service_id,
            duration_minutes=payload.duration_minutes,
            worker_id=payload.worker_id,
            preferred_date=payload.preferred_date,
            preferred_time_window=payload.preferred_time_window,
            days_ahead=payload.days_ahead,
            max_slots=payload.max_slots,
        )
    except (SchedulingError, GoogleAuthorizationRequired) as exc:
        _raise_http_error(exc)
    return AgentProposeSlotsResponse(
        slots=[
            AgentSlotResponse(
                worker_id=slot.worker_id,
                worker_name=slot.worker_name,
                calendar_id=slot.calendar_id,
                start_at=slot.start_at,
                end_at=slot.end_at,
                blocked_start_at=slot.blocked_start_at,
                blocked_end_at=slot.blocked_end_at,
            )
            for slot in slots
        ]
    )


@router.post(
    "/create_appointment",
    response_model=AgentAppointmentConfirmation,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_appointment(
    payload: AgentCreateAppointmentRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentAppointmentConfirmation:
    """Create one appointment atomically across Google and PostgreSQL."""
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            payload.clinic_id,
        )
        appointment = create_appointment_transactional(
            session,
            client,
            clinic_id=payload.clinic_id,
            worker_id=payload.worker_id,
            service_id=payload.service_id,
            patient_name=payload.patient_name,
            patient_phone=payload.patient_phone,
            reason=payload.reason,
            start_at=payload.start_at,
            end_at=payload.end_at,
            call_session_id=payload.call_session_id,
            idempotency_key=payload.idempotency_key,
        )
    except (
        AgentAppointmentError,
        GoogleAuthorizationRequired,
    ) as exc:
        _raise_http_error(exc)
    return AgentAppointmentConfirmation(
        status="confirmed",
        appointment_id=appointment.id,
        clinic_id=appointment.clinic_id,
        worker_id=appointment.worker_id,
        worker_name=appointment.worker.name,
        service_id=appointment.service_id,
        patient_name=appointment.patient_name,
        patient_phone=appointment.patient_phone,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        google_calendar_id=appointment.google_calendar_id,
        google_event_id=appointment.google_event_id,
    )


@router.post(
    "/cancel_appointment",
    response_model=AgentCancellationConfirmation,
)
def cancel_agent_appointment(
    payload: AgentCancelAppointmentRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentCancellationConfirmation:
    """Delete the Google event and soft-cancel its database record."""
    try:
        client = get_authorized_calendar_client(
            session,
            settings,
            payload.clinic_id,
        )
        appointment, already_cancelled = cancel_appointment_transactional(
            session,
            client,
            clinic_id=payload.clinic_id,
            appointment_id=payload.appointment_id,
            patient_phone=payload.patient_phone,
            approximate_date=payload.approximate_date,
        )
    except (
        AgentAppointmentError,
        GoogleAuthorizationRequired,
    ) as exc:
        _raise_http_error(exc)
    return AgentCancellationConfirmation(
        status="already_cancelled" if already_cancelled else "cancelled",
        appointment_id=appointment.id,
        patient_name=appointment.patient_name,
        patient_phone=appointment.patient_phone,
        start_at=appointment.start_at,
        worker_id=appointment.worker_id,
        google_event_id=appointment.google_event_id,
    )


@router.post("/get_clinic_info", response_model=AgentClinicInfoResponse)
def get_clinic_info(
    payload: AgentClinicInfoRequest,
    session: Annotated[Session, Depends(get_db)],
) -> AgentClinicInfoResponse:
    """Return active clinic, worker, and service information."""
    clinic = session.get(Clinic, payload.clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found.",
        )
    workers = session.scalars(
        select(Worker)
        .where(Worker.clinic_id == clinic.id, Worker.is_active.is_(True))
        .order_by(Worker.name)
    )
    services = session.scalars(
        select(Service)
        .where(
            Service.clinic_id == clinic.id,
            Service.is_active.is_(True),
            Service.is_bookable_by_bot.is_(True),
        )
        .order_by(Service.name)
    )
    return AgentClinicInfoResponse(
        id=clinic.id,
        name=clinic.name,
        timezone=clinic.timezone,
        phone_number=clinic.phone_number,
        workers=[
            AgentWorkerInfo(
                id=worker.id,
                name=worker.name,
                role=worker.role,
                is_active=worker.is_active,
                calendar_linked=worker.calendar_id is not None,
            )
            for worker in workers
        ],
        services=[
            AgentServiceInfo(
                id=service.id,
                name=service.name,
                duration_minutes=service.duration_minutes,
                buffer_before_minutes=service.buffer_before_minutes,
                buffer_after_minutes=service.buffer_after_minutes,
            )
            for service in services
        ],
    )
