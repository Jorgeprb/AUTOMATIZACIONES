"""Administrative call, conversation, and appointment endpoints."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.admin_schemas import (
    AppointmentAnalysisRead,
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    CallAnalysisDetail,
    CallAnalysisRead,
    CallAppointmentRead,
    CallCreate,
    CallDebugResponse,
    CallEventRead,
    CallPrivacyResponse,
    CallRead,
    CallUpdate,
    DeleteResponse,
    Page,
    TranscriptTurnRead,
)
from app.api.admin.common import (
    apply_update,
    clinic_or_404,
    commit_or_conflict,
    nested_or_404,
    paginate,
    set_values,
)
from app.calendar.appointment_service import (
    AgentAppointmentError,
    cancel_appointment_transactional,
)
from app.calendar.google_client import (
    GoogleAuthorizationRequired,
    get_authorized_calendar_client,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    Appointment,
    AppointmentSource,
    AppointmentStatus,
    AssistantConfig,
    CallEvent,
    CallOutcome,
    CallSession,
    CallStatus,
    PhoneNumber,
    Service,
    Worker,
)

router = APIRouter(prefix="/admin")


def _call_model_or_404(
    session: Session,
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
) -> CallSession:
    """Return one tenant-owned call model for mutations."""
    return nested_or_404(
        session,
        CallSession,
        clinic_id=clinic_id,
        resource_id=call_id,
        label="Call session",
    )


def _appointment_summary(appointment: Appointment) -> CallAppointmentRead:
    """Map one linked appointment with public relation names."""
    return CallAppointmentRead(
        id=appointment.id,
        worker_id=appointment.worker_id,
        worker_name=appointment.worker.name,
        service_id=appointment.service_id,
        service_name=(
            appointment.service.public_name if appointment.service is not None else None
        ),
        patient_name=appointment.patient_name,
        patient_phone=appointment.patient_phone,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        status=appointment.status,
        source=appointment.source,
        google_event_id=appointment.google_event_id,
    )


def _call_analysis(call: CallSession) -> CallAnalysisRead:
    """Map one call with its first linked appointment and duration."""
    appointment = min(
        call.appointments,
        key=lambda item: item.created_at,
        default=None,
    )
    duration_seconds = (
        max(0, int((call.ended_at - call.started_at).total_seconds()))
        if call.ended_at is not None
        else None
    )
    values = CallRead.model_validate(call).model_dump()
    return CallAnalysisRead(
        **values,
        duration_seconds=duration_seconds,
        appointment_created=appointment is not None,
        appointment=(
            _appointment_summary(appointment) if appointment is not None else None
        ),
    )


def _is_tool_event(event: CallEvent) -> bool:
    """Identify persisted function calls and tool outputs."""
    event_type = event.event_type.casefold()
    payload_type = str(event.payload_json.get("type", "")).casefold()
    item = event.payload_json.get("item")
    item_type = str(item.get("type", "")).casefold() if isinstance(item, dict) else ""
    return (
        "function_call" in event_type
        or "tool_call" in event_type
        or "function_call" in payload_type
        or item_type in {"function_call", "function_call_output"}
    )


def _is_error_event(event: CallEvent) -> bool:
    """Identify Realtime or local error events."""
    event_type = event.event_type.casefold()
    return (
        event_type == "error" or event_type.endswith(".error") or "failed" in event_type
    )


def _call_detail(call: CallSession) -> CallAnalysisDetail:
    """Build the complete classified analysis response."""
    base = _call_analysis(call).model_dump()
    events = [CallEventRead.model_validate(event) for event in call.events]
    return CallAnalysisDetail(
        **base,
        clinic_name=(
            call.clinic.name if call.clinic is not None else "Clínica eliminada"
        ),
        events=events,
        tool_calls=[
            CallEventRead.model_validate(event)
            for event in call.events
            if _is_tool_event(event)
        ],
        errors=[
            CallEventRead.model_validate(event)
            for event in call.events
            if _is_error_event(event)
        ],
    )


def _transcript_turns(transcript_text: str | None) -> list[TranscriptTurnRead]:
    """Parse the stored plain transcript into export-friendly turns."""
    turns: list[TranscriptTurnRead] = []
    for raw_line in (transcript_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        speaker, separator, content = line.partition(":")
        if not separator:
            turns.append(
                TranscriptTurnRead(role="unknown", speaker="Desconocido", text=line)
            )
            continue
        normalized = speaker.strip().casefold()
        role = (
            "user"
            if normalized in {"paciente", "usuario", "caller", "user"}
            else "assistant"
            if normalized in {"asistente", "assistant", "bot"}
            else "unknown"
        )
        turns.append(
            TranscriptTurnRead(
                role=role,
                speaker=speaker.strip(),
                text=content.strip(),
            )
        )
    return turns


def _redact_value(value: object, old_phone: str) -> object:
    """Recursively remove a caller phone from stored diagnostic payloads."""
    if isinstance(value, str):
        return value.replace(old_phone, "[ANONYMIZED]")
    if isinstance(value, list):
        return [_redact_value(item, old_phone) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, old_phone) for key, item in value.items()}
    return value


def _anonymize_call(session: Session, call: CallSession, *, clear_events: bool) -> None:
    """Remove personal conversation data while preserving appointment links."""
    old_phone = call.caller_phone
    call.caller_phone = "anonymized"
    call.caller_name = None
    call.provider_call_id = None
    call.transcript_text = None
    call.summary_text = None
    call.transcript_enabled = False
    if clear_events:
        for event in list(call.events):
            session.delete(event)
        call.conversation_state_json = {"anonymized": True}
    else:
        call.conversation_state_json = _redact_value(
            call.conversation_state_json,
            old_phone,
        )  # type: ignore[assignment]
        for event in call.events:
            event.payload_json = _redact_value(
                event.payload_json,
                old_phone,
            )  # type: ignore[assignment]


def _appointment_analysis(appointment: Appointment) -> AppointmentAnalysisRead:
    """Map one appointment with relation names used by the panel."""
    values = AppointmentRead.model_validate(appointment).model_dump()
    return AppointmentAnalysisRead(
        **values,
        worker_name=appointment.worker.name,
        service_name=(
            appointment.service.public_name if appointment.service is not None else None
        ),
    )


def _call_relations(
    session: Session,
    clinic_id: uuid.UUID,
    *,
    phone_number_id: uuid.UUID | None,
    assistant_config_id: uuid.UUID | None,
) -> None:
    """Validate optional call configuration relations."""
    if phone_number_id is not None:
        nested_or_404(
            session,
            PhoneNumber,
            clinic_id=clinic_id,
            resource_id=phone_number_id,
            label="Phone number",
        )
    if assistant_config_id is not None:
        nested_or_404(
            session,
            AssistantConfig,
            clinic_id=clinic_id,
            resource_id=assistant_config_id,
            label="Assistant configuration",
        )


def _appointment_relations(
    session: Session,
    clinic_id: uuid.UUID,
    *,
    worker_id: uuid.UUID,
    service_id: uuid.UUID | None,
    call_session_id: uuid.UUID | None,
) -> Worker:
    """Validate that every appointment relation belongs to the clinic."""
    worker = nested_or_404(
        session,
        Worker,
        clinic_id=clinic_id,
        resource_id=worker_id,
        label="Worker",
    )
    if service_id is not None:
        nested_or_404(
            session,
            Service,
            clinic_id=clinic_id,
            resource_id=service_id,
            label="Service",
        )
    if call_session_id is not None:
        nested_or_404(
            session,
            CallSession,
            clinic_id=clinic_id,
            resource_id=call_session_id,
            label="Call session",
        )
    return worker


def _ensure_appointment_slot_free(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    start_at: object,
    end_at: object,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Reject local appointment overlaps for one worker."""
    statement = select(Appointment.id).where(
        Appointment.clinic_id == clinic_id,
        Appointment.worker_id == worker_id,
        Appointment.status.in_(
            [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]
        ),
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if exclude_id is not None:
        statement = statement.where(Appointment.id != exclude_id)
    if session.scalar(statement) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The worker already has an appointment in this time range.",
        )


@router.get(
    "/clinics/{clinic_id}/calls",
    response_model=Page[CallAnalysisRead],
    tags=["Admin · Calls and conversations"],
)
def list_calls(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    active: bool | None = Query(default=None),
    call_date: Annotated[date | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    outcome: Annotated[CallOutcome | None, Query()] = None,
    status_filter: Annotated[
        CallStatus | None,
        Query(alias="status"),
    ] = None,
    phone: str | None = Query(default=None, min_length=1, max_length=32),
    worker_id: Annotated[uuid.UUID | None, Query()] = None,
    service_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[CallAnalysisRead]:
    """List clinic calls with conversation outcome filters."""
    clinic = clinic_or_404(session, clinic_id)
    statement = (
        select(CallSession)
        .options(
            selectinload(CallSession.appointments).selectinload(Appointment.worker),
            selectinload(CallSession.appointments).selectinload(Appointment.service),
        )
        .where(CallSession.clinic_id == clinic_id)
    )
    if active is True:
        statement = statement.where(
            CallSession.status.in_([CallStatus.INCOMING, CallStatus.ACTIVE])
        )
    elif active is False:
        statement = statement.where(
            CallSession.status.in_(
                [
                    CallStatus.COMPLETED,
                    CallStatus.FAILED,
                    CallStatus.TRANSFERRED,
                ]
            )
        )
    if call_date is not None:
        statement = statement.where(
            func.date(func.timezone(clinic.timezone, CallSession.started_at))
            == call_date
        )
    if date_from is not None:
        statement = statement.where(
            func.date(func.timezone(clinic.timezone, CallSession.started_at))
            >= date_from
        )
    if date_to is not None:
        statement = statement.where(
            func.date(func.timezone(clinic.timezone, CallSession.started_at)) <= date_to
        )
    if outcome is not None:
        statement = statement.where(CallSession.outcome == outcome)
    if status_filter is not None:
        statement = statement.where(CallSession.status == status_filter)
    if phone:
        statement = statement.where(
            CallSession.caller_phone.ilike(f"%{phone.strip()}%")
        )
    if worker_id is not None:
        statement = statement.where(
            CallSession.appointments.any(Appointment.worker_id == worker_id)
        )
    if service_id is not None:
        statement = statement.where(
            CallSession.appointments.any(Appointment.service_id == service_id)
        )
    ordered = statement.order_by(CallSession.started_at.desc(), CallSession.id)
    total = (
        session.scalar(
            select(func.count()).select_from(ordered.order_by(None).subquery())
        )
        or 0
    )
    rows = session.scalars(
        ordered.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[CallAnalysisRead](
        items=[_call_analysis(call) for call in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.post(
    "/clinics/{clinic_id}/calls",
    response_model=CallRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Calls and conversations"],
)
def create_call(
    clinic_id: uuid.UUID,
    payload: CallCreate,
    session: Annotated[Session, Depends(get_db)],
) -> CallSession:
    """Create or import one call record for administrative workflows."""
    clinic_or_404(session, clinic_id)
    _call_relations(
        session,
        clinic_id,
        phone_number_id=payload.phone_number_id,
        assistant_config_id=payload.assistant_config_id,
    )
    call = CallSession(clinic_id=clinic_id, **payload.model_dump())
    session.add(call)
    commit_or_conflict(session)
    session.refresh(call)
    return call


@router.get(
    "/clinics/{clinic_id}/calls/{call_id}",
    response_model=CallAnalysisDetail,
    tags=["Admin · Calls and conversations"],
)
def get_call(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CallAnalysisDetail:
    """Get one call with its stored raw conversation events."""
    call = session.scalar(
        select(CallSession)
        .options(
            selectinload(CallSession.appointments).selectinload(Appointment.worker),
            selectinload(CallSession.appointments).selectinload(Appointment.service),
            selectinload(CallSession.events),
            selectinload(CallSession.clinic),
        )
        .where(
            CallSession.id == call_id,
            CallSession.clinic_id == clinic_id,
        )
    )
    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call session not found.",
        )
    return _call_detail(call)


@router.get(
    "/clinics/{clinic_id}/calls/{call_id}/events",
    response_model=Page[CallEventRead],
    tags=["Admin · Calls and conversations"],
)
def list_call_events(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[CallEventRead]:
    """List the raw event timeline for one call conversation."""
    _call_model_or_404(session, clinic_id, call_id)
    statement = select(CallEvent).where(CallEvent.call_session_id == call_id)
    return paginate(
        session,
        statement.order_by(CallEvent.created_at, CallEvent.id),
        schema=CallEventRead,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/clinics/{clinic_id}/calls/{call_id}/tool-calls",
    response_model=list[CallEventRead],
    tags=["Admin · Calls and conversations"],
)
def list_call_tool_calls(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> list[CallEventRead]:
    """List persisted Realtime function-call and tool-output events."""
    _call_model_or_404(session, clinic_id, call_id)
    events = session.scalars(
        select(CallEvent)
        .where(CallEvent.call_session_id == call_id)
        .order_by(CallEvent.created_at, CallEvent.id)
    ).all()
    return [
        CallEventRead.model_validate(event) for event in events if _is_tool_event(event)
    ]


@router.patch(
    "/clinics/{clinic_id}/calls/{call_id}",
    response_model=CallRead,
    tags=["Admin · Calls and conversations"],
)
def update_call(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    payload: CallUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> CallSession:
    """Update call metadata, transcript controls, or business outcome."""
    call = _call_model_or_404(session, clinic_id, call_id)
    fields = payload.model_fields_set
    phone_number_id = (
        payload.phone_number_id if "phone_number_id" in fields else call.phone_number_id
    )
    assistant_config_id = (
        payload.assistant_config_id
        if "assistant_config_id" in fields
        else call.assistant_config_id
    )
    _call_relations(
        session,
        clinic_id,
        phone_number_id=phone_number_id,
        assistant_config_id=assistant_config_id,
    )
    apply_update(call, payload)
    commit_or_conflict(session)
    session.refresh(call)
    return call


@router.delete(
    "/clinics/{clinic_id}/calls/{call_id}/content",
    response_model=CallPrivacyResponse,
    tags=["Admin · Calls and conversations"],
)
def delete_call_content(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CallPrivacyResponse:
    """Delete transcript and summary while preserving call and appointment."""
    call = _call_model_or_404(session, clinic_id, call_id)
    call.transcript_text = None
    call.summary_text = None
    call.transcript_enabled = False
    commit_or_conflict(session)
    return CallPrivacyResponse(
        status="content_deleted",
        call_session_id=call.id,
        appointment_preserved=bool(call.appointments),
    )


@router.post(
    "/clinics/{clinic_id}/calls/{call_id}/anonymize-phone",
    response_model=CallPrivacyResponse,
    tags=["Admin · Calls and conversations"],
)
def anonymize_call_phone(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CallPrivacyResponse:
    """Anonymize caller identity without touching linked appointments."""
    call = _call_model_or_404(session, clinic_id, call_id)
    _anonymize_call(session, call, clear_events=False)
    commit_or_conflict(session)
    return CallPrivacyResponse(
        status="phone_anonymized",
        call_session_id=call.id,
        appointment_preserved=bool(call.appointments),
    )


@router.get(
    "/clinics/{clinic_id}/calls/{call_id}/debug",
    response_model=CallDebugResponse,
    tags=["Admin · Calls and conversations"],
)
def get_call_debug(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CallDebugResponse:
    """Return a downloadable structured debug snapshot."""
    detail = get_call(clinic_id, call_id, session)
    return CallDebugResponse(
        call=detail,
        transcript_text=detail.transcript_text,
        transcript=_transcript_turns(detail.transcript_text),
        generated_at=datetime.now(UTC),
    )


@router.delete(
    "/clinics/{clinic_id}/calls/{call_id}",
    response_model=CallPrivacyResponse,
    tags=["Admin · Calls and conversations"],
)
def delete_call(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CallPrivacyResponse:
    """Delete an unlinked call or anonymize it when an appointment exists."""
    call = _call_model_or_404(session, clinic_id, call_id)
    has_appointment = bool(call.appointments)
    if has_appointment:
        _anonymize_call(session, call, clear_events=True)
        result_status = "anonymized"
    else:
        session.delete(call)
        result_status = "deleted"
    commit_or_conflict(session)
    return CallPrivacyResponse(
        status=result_status,
        call_session_id=call_id,
        appointment_preserved=has_appointment,
    )


@router.get(
    "/clinics/{clinic_id}/appointments",
    response_model=Page[AppointmentAnalysisRead],
    tags=["Admin · Appointments"],
)
def list_appointments(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    appointment_date: Annotated[
        date | None,
        Query(alias="date"),
    ] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    worker_id: Annotated[uuid.UUID | None, Query()] = None,
    service_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[
        AppointmentStatus | None,
        Query(alias="status"),
    ] = None,
    patient_phone: str | None = Query(default=None, min_length=1, max_length=32),
    source: Annotated[AppointmentSource | None, Query()] = None,
) -> Page[AppointmentAnalysisRead]:
    """List appointments with date, worker, service, and status filters."""
    clinic = clinic_or_404(session, clinic_id)
    statement = (
        select(Appointment)
        .options(
            selectinload(Appointment.worker),
            selectinload(Appointment.service),
        )
        .where(Appointment.clinic_id == clinic_id)
    )
    if appointment_date is not None:
        statement = statement.where(
            func.date(func.timezone(clinic.timezone, Appointment.start_at))
            == appointment_date
        )
    if date_from is not None:
        statement = statement.where(
            func.date(func.timezone(clinic.timezone, Appointment.start_at)) >= date_from
        )
    if date_to is not None:
        statement = statement.where(
            func.date(func.timezone(clinic.timezone, Appointment.start_at)) <= date_to
        )
    if worker_id is not None:
        statement = statement.where(Appointment.worker_id == worker_id)
    if service_id is not None:
        statement = statement.where(Appointment.service_id == service_id)
    if status_filter is not None:
        statement = statement.where(Appointment.status == status_filter)
    if patient_phone:
        statement = statement.where(
            Appointment.patient_phone.ilike(f"%{patient_phone.strip()}%")
        )
    if source is not None:
        statement = statement.where(Appointment.source == source)
    ordered = statement.order_by(Appointment.start_at.desc(), Appointment.id)
    total = (
        session.scalar(
            select(func.count()).select_from(ordered.order_by(None).subquery())
        )
        or 0
    )
    rows = session.scalars(
        ordered.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[AppointmentAnalysisRead](
        items=[_appointment_analysis(appointment) for appointment in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.post(
    "/clinics/{clinic_id}/appointments",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Appointments"],
)
def create_appointment(
    clinic_id: uuid.UUID,
    payload: AppointmentCreate,
    session: Annotated[Session, Depends(get_db)],
) -> Appointment:
    """Create a local panel appointment without calling Google Calendar."""
    clinic_or_404(session, clinic_id)
    worker = _appointment_relations(
        session,
        clinic_id,
        worker_id=payload.worker_id,
        service_id=payload.service_id,
        call_session_id=payload.call_session_id,
    )
    _ensure_appointment_slot_free(
        session,
        clinic_id=clinic_id,
        worker_id=payload.worker_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )
    appointment_id = uuid.uuid4()
    appointment = Appointment(
        id=appointment_id,
        clinic_id=clinic_id,
        worker_id=payload.worker_id,
        service_id=payload.service_id,
        call_session_id=payload.call_session_id,
        google_calendar_id=worker.calendar_id or f"admin:{worker.id}",
        google_event_id=f"admin:{appointment_id}",
        patient_name=payload.patient_name,
        patient_phone=payload.patient_phone,
        reason=payload.reason,
        start_at=payload.start_at,
        end_at=payload.end_at,
        status=payload.status,
        source=AppointmentSource.ADMIN_PANEL,
    )
    session.add(appointment)
    commit_or_conflict(session)
    session.refresh(appointment)
    return appointment


@router.get(
    "/clinics/{clinic_id}/appointments/{appointment_id}",
    response_model=AppointmentRead,
    tags=["Admin · Appointments"],
)
def get_appointment(
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> Appointment:
    """Get one clinic appointment."""
    return nested_or_404(
        session,
        Appointment,
        clinic_id=clinic_id,
        resource_id=appointment_id,
        label="Appointment",
    )


@router.patch(
    "/clinics/{clinic_id}/appointments/{appointment_id}",
    response_model=AppointmentRead,
    tags=["Admin · Appointments"],
)
def update_appointment(
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    payload: AppointmentUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> Appointment:
    """Partially update one local appointment."""
    appointment = get_appointment(clinic_id, appointment_id, session)
    fields = payload.model_fields_set
    worker_id = payload.worker_id if "worker_id" in fields else appointment.worker_id
    service_id = (
        payload.service_id if "service_id" in fields else appointment.service_id
    )
    call_session_id = (
        payload.call_session_id
        if "call_session_id" in fields
        else appointment.call_session_id
    )
    start_at = payload.start_at or appointment.start_at
    end_at = payload.end_at or appointment.end_at
    if end_at <= start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_at must be after start_at.",
        )
    if worker_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="worker_id cannot be null.",
        )
    _appointment_relations(
        session,
        clinic_id,
        worker_id=worker_id,
        service_id=service_id,
        call_session_id=call_session_id,
    )
    target_status = payload.status or appointment.status
    if target_status in {AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED}:
        _ensure_appointment_slot_free(
            session,
            clinic_id=clinic_id,
            worker_id=worker_id,
            start_at=start_at,
            end_at=end_at,
            exclude_id=appointment.id,
        )
    values = payload.model_dump(exclude_unset=True)
    set_values(appointment, values)
    commit_or_conflict(session)
    session.refresh(appointment)
    return appointment


@router.post(
    "/clinics/{clinic_id}/appointments/{appointment_id}/cancel",
    response_model=AppointmentAnalysisRead,
    tags=["Admin · Appointments"],
)
def cancel_appointment(
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AppointmentAnalysisRead:
    """Cancel locally created appointments or remove their Google event first."""
    appointment = get_appointment(clinic_id, appointment_id, session)
    if appointment.status is not AppointmentStatus.CANCELLED:
        if appointment.source is AppointmentSource.ADMIN_PANEL or (
            appointment.google_event_id.startswith("admin:")
        ):
            appointment.status = AppointmentStatus.CANCELLED
            commit_or_conflict(session)
        else:
            try:
                client = get_authorized_calendar_client(session, settings, clinic_id)
                cancel_appointment_transactional(
                    session,
                    client,
                    clinic_id=clinic_id,
                    appointment_id=appointment_id,
                    patient_phone=None,
                    approximate_date=None,
                )
            except GoogleAuthorizationRequired as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc
            except AgentAppointmentError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc
    refreshed = session.scalar(
        select(Appointment)
        .options(
            selectinload(Appointment.worker),
            selectinload(Appointment.service),
        )
        .where(
            Appointment.id == appointment_id,
            Appointment.clinic_id == clinic_id,
        )
        .execution_options(populate_existing=True)
    )
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found.",
        )
    return _appointment_analysis(refreshed)


@router.delete(
    "/clinics/{clinic_id}/appointments/{appointment_id}",
    response_model=DeleteResponse,
    tags=["Admin · Appointments"],
)
def delete_appointment(
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one local appointment record without calling Google Calendar."""
    appointment = get_appointment(clinic_id, appointment_id, session)
    session.delete(appointment)
    commit_or_conflict(session)
    return DeleteResponse(id=appointment_id)
