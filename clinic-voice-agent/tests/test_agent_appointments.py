"""Transactional tests for the internal voice-agent appointment tools."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.calendar.appointment_service import (
    AppointmentPersistenceFailed,
    AppointmentUnavailable,
    CalendarOperationFailed,
    cancel_appointment_transactional,
    create_appointment_transactional,
)
from app.main import create_app
from app.models import (
    Appointment,
    AppointmentStatus,
    CallSession,
    Clinic,
    ClinicResource,
    ResourceReservation,
    Service,
    ServiceResourceRequirement,
    Worker,
)

MADRID = ZoneInfo("Europe/Madrid")
START_AT = datetime(2026, 6, 22, 9, 0, tzinfo=MADRID)
END_AT = START_AT + timedelta(minutes=30)


def _working_hours() -> dict[str, list[dict[str, str]]]:
    """Return a Monday schedule containing the test slot."""
    return {
        "monday": [{"start": "09:00", "end": "14:00"}],
        "tuesday": [],
        "wednesday": [],
        "thursday": [],
        "friday": [],
        "saturday": [],
        "sunday": [],
    }


def _domain(session: Session) -> tuple[Clinic, Worker, Service]:
    """Persist one clinic, worker, and service."""
    clinic = Clinic(
        name="Clínica Agent",
        timezone="Europe/Madrid",
        phone_number="+34919999999",
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@calendar.test",
        color_id="2",
        working_hours_json=_working_hours(),
    )
    service = Service(
        clinic=clinic,
        name="Consulta general",
        duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
    )
    session.add_all([clinic, worker, service])
    session.commit()
    return clinic, worker, service


def _calendar_client(
    *,
    busy: list[tuple[datetime, datetime]] | None = None,
    insert_error: Exception | None = None,
    delete_error: Exception | None = None,
) -> MagicMock:
    """Build a Google Calendar mock for FreeBusy and event operations."""
    client = MagicMock()

    def freebusy_execute() -> dict[str, Any]:
        body = client.freebusy.return_value.query.call_args.kwargs["body"]
        return {
            "calendars": {
                item["id"]: {
                    "busy": [
                        {
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                        }
                        for start, end in (busy or [])
                    ]
                }
                for item in body["items"]
            }
        }

    def insert_execute() -> dict[str, str]:
        if insert_error is not None:
            raise insert_error
        body = client.events.return_value.insert.call_args.kwargs["body"]
        return {"id": str(body["id"])}

    def delete_execute() -> None:
        if delete_error is not None:
            raise delete_error

    client.freebusy.return_value.query.return_value.execute.side_effect = (
        freebusy_execute
    )
    client.events.return_value.insert.return_value.execute.side_effect = insert_execute
    client.events.return_value.delete.return_value.execute.side_effect = delete_execute
    return client


def _create(
    session: Session,
    client: MagicMock,
    clinic: Clinic,
    worker: Worker,
    service: Service,
    *,
    call_session_id: uuid.UUID | None = None,
) -> Appointment:
    """Create the standard test appointment."""
    return create_appointment_transactional(
        session,
        client,
        clinic_id=clinic.id,
        worker_id=worker.id,
        service_id=service.id,
        patient_name="Paciente Uno",
        patient_phone="+34600000001",
        reason="Revisión general",
        start_at=START_AT,
        end_at=END_AT,
        call_session_id=call_session_id,
    )


def test_create_appointment_ok(db_session: Session) -> None:
    """Creation should persist a confirmed row and the required Google event."""
    clinic, worker, service = _domain(db_session)
    client = _calendar_client()
    call_session = CallSession(
        openai_call_id="rtc-agent-test",
        caller_phone="+34600000001",
        called_number=clinic.phone_number,
    )
    db_session.add(call_session)
    db_session.commit()

    appointment = _create(
        db_session,
        client,
        clinic,
        worker,
        service,
        call_session_id=call_session.id,
    )

    persisted = db_session.get(Appointment, appointment.id)
    event_body = client.events.return_value.insert.call_args.kwargs["body"]
    assert persisted is not None
    assert persisted.status is AppointmentStatus.CONFIRMED
    assert persisted.google_event_id == appointment.id.hex
    assert event_body["summary"] == "Cita - Paciente Uno"
    assert event_body["colorId"] == "2"
    assert "Teléfono: +34600000001" in event_body["description"]
    assert "Motivo general: Revisión general" in event_body["description"]
    assert event_body["extendedProperties"]["private"] == {
        "worker_id": str(worker.id),
        "source": "voice_bot",
        "appointment_id": str(appointment.id),
        "call_session_id": str(call_session.id),
    }


def test_create_appointment_fails_when_slot_is_busy(
    db_session: Session,
) -> None:
    """A FreeBusy conflict must prevent Google and database insertion."""
    clinic, worker, service = _domain(db_session)
    client = _calendar_client(busy=[(START_AT, END_AT)])

    with pytest.raises(AppointmentUnavailable):
        _create(db_session, client, clinic, worker, service)

    assert db_session.scalar(select(func.count()).select_from(Appointment)) == 0
    client.events.return_value.insert.assert_not_called()


def test_cancel_appointment_ok(db_session: Session) -> None:
    """Cancellation should delete the event and soft-cancel the row."""
    clinic, worker, service = _domain(db_session)
    client = _calendar_client()
    appointment = _create(db_session, client, clinic, worker, service)

    cancelled, already_cancelled = cancel_appointment_transactional(
        db_session,
        client,
        clinic_id=clinic.id,
        appointment_id=appointment.id,
        patient_phone=None,
        approximate_date=None,
    )

    assert not already_cancelled
    assert cancelled.status is AppointmentStatus.CANCELLED
    assert db_session.get(Appointment, appointment.id) is not None
    client.events.return_value.delete.assert_called_with(
        calendarId=worker.calendar_id,
        eventId=appointment.google_event_id,
        sendUpdates="none",
    )


def test_cancel_appointment_by_phone_and_approximate_date(
    db_session: Session,
) -> None:
    """The fallback lookup should choose the matching nearby appointment."""
    clinic, worker, service = _domain(db_session)
    client = _calendar_client()
    appointment = _create(db_session, client, clinic, worker, service)

    cancelled, _ = cancel_appointment_transactional(
        db_session,
        client,
        clinic_id=clinic.id,
        appointment_id=None,
        patient_phone=appointment.patient_phone,
        approximate_date=appointment.start_at.astimezone(MADRID).date(),
    )

    assert cancelled.id == appointment.id
    assert cancelled.status is AppointmentStatus.CANCELLED


def test_google_failure_does_not_persist_appointment(
    db_session: Session,
) -> None:
    """A failed event insertion must leave PostgreSQL unchanged."""
    clinic, worker, service = _domain(db_session)
    client = _calendar_client(insert_error=RuntimeError("Google unavailable"))

    with pytest.raises(CalendarOperationFailed):
        _create(db_session, client, clinic, worker, service)

    assert db_session.scalar(select(func.count()).select_from(Appointment)) == 0


def test_db_failure_after_google_insert_attempts_compensation(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database failure after insertion must delete the Google event."""
    clinic, worker, service = _domain(db_session)
    client = _calendar_client()
    original_flush = db_session.flush

    def failing_flush(objects: Sequence[Any] | None = None) -> None:
        if any(isinstance(item, Appointment) for item in db_session.new):
            raise SQLAlchemyError("database write failed")
        original_flush(objects)

    monkeypatch.setattr(db_session, "flush", failing_flush)

    with pytest.raises(AppointmentPersistenceFailed):
        _create(db_session, client, clinic, worker, service)

    client.events.return_value.delete.assert_called_once()
    assert db_session.scalar(select(func.count()).select_from(Appointment)) == 0


def test_google_delete_failure_keeps_appointment_confirmed(
    db_session: Session,
) -> None:
    """A failed Google cancellation must roll back the local status change."""
    clinic, worker, service = _domain(db_session)
    create_client = _calendar_client()
    appointment = _create(
        db_session,
        create_client,
        clinic,
        worker,
        service,
    )
    cancel_client = _calendar_client(delete_error=RuntimeError("Google unavailable"))

    with pytest.raises(CalendarOperationFailed):
        cancel_appointment_transactional(
            db_session,
            cancel_client,
            clinic_id=clinic.id,
            appointment_id=appointment.id,
            patient_phone=None,
            approximate_date=None,
        )

    db_session.expire_all()
    persisted = db_session.get(Appointment, appointment.id)
    assert persisted is not None
    assert persisted.status is AppointmentStatus.CONFIRMED


def test_agent_routes_are_registered() -> None:
    """All internal tool endpoints should be visible in OpenAPI."""
    paths = set(create_app().openapi()["paths"])

    assert "/api/agent/check_availability" in paths
    assert "/api/agent/propose_slots" in paths
    assert "/api/agent/create_appointment" in paths
    assert "/api/agent/cancel_appointment" in paths
    assert "/api/agent/get_clinic_info" in paths


def test_create_appointment_idempotency_returns_existing_without_second_google_event(
    db_session: Session,
) -> None:
    clinic, worker, service = _domain(db_session)
    client = _calendar_client()
    kwargs = dict(
        clinic_id=clinic.id,
        worker_id=worker.id,
        service_id=service.id,
        patient_name="Paciente Uno",
        patient_phone="+34 600 000 001",
        reason="Revisión general",
        start_at=START_AT,
        end_at=END_AT,
        call_session_id=None,
        idempotency_key="test-call:tool-call:create-appointment",
    )
    first = create_appointment_transactional(db_session, client, **kwargs)
    second = create_appointment_transactional(db_session, client, **kwargs)
    assert second.id == first.id
    assert second.patient_phone == "+34600000001"
    assert client.events.return_value.insert.call_count == 1


def test_cancelled_appointment_releases_resource_capacity(
    db_session: Session,
) -> None:
    clinic, worker, service = _domain(db_session)
    resource = ClinicResource(
        clinic_id=clinic.id,
        name="Consulta 1",
        resource_type="room",
        capacity=1,
    )
    db_session.add(resource)
    db_session.flush()
    db_session.add(
        ServiceResourceRequirement(
            clinic_id=clinic.id,
            service_id=service.id,
            resource_id=resource.id,
            quantity=1,
        )
    )
    db_session.commit()
    client = _calendar_client()

    first = _create(db_session, client, clinic, worker, service)
    assert db_session.scalar(select(func.count(ResourceReservation.id))) == 1
    cancel_appointment_transactional(
        db_session,
        client,
        clinic_id=clinic.id,
        appointment_id=first.id,
        patient_phone=None,
        approximate_date=None,
    )

    replacement = _create(db_session, client, clinic, worker, service)
    assert replacement.id != first.id


def test_shared_resources_are_locked_in_deterministic_order(
    database_engine: Engine,
) -> None:
    if database_engine.dialect.name != "postgresql":
        pytest.skip("Row-lock ordering requires PostgreSQL.")

    factory = sessionmaker(
        bind=database_engine,
        class_=Session,
        expire_on_commit=False,
    )
    low_resource_id = uuid.UUID(int=1001)
    high_resource_id = uuid.UUID(int=1002)
    with factory() as session:
        clinic = Clinic(
            id=uuid.uuid4(),
            name="Clínica Recursos Concurrentes",
            timezone="Europe/Madrid",
            phone_number="+34919999998",
        )
        workers = [
            Worker(
                clinic=clinic,
                name=f"Profesional {index}",
                role="Médica",
                calendar_id=f"worker-{index}@calendar.test",
                working_hours_json=_working_hours(),
            )
            for index in (1, 2)
        ]
        services = [
            Service(
                clinic=clinic,
                name=f"Servicio {index}",
                duration_minutes=30,
            )
            for index in (1, 2)
        ]
        resources = [
            ClinicResource(
                id=resource_id,
                clinic_id=clinic.id,
                name=name,
                resource_type="equipment",
                capacity=2,
            )
            for resource_id, name in (
                (low_resource_id, "Recurso bajo"),
                (high_resource_id, "Recurso alto"),
            )
        ]
        session.add_all([clinic, *workers, *services, *resources])
        session.flush()
        for service, resource in (
            (services[0], resources[0]),
            (services[1], resources[1]),
            (services[0], resources[1]),
            (services[1], resources[0]),
        ):
            session.add(
                ServiceResourceRequirement(
                    clinic_id=clinic.id,
                    service_id=service.id,
                    resource_id=resource.id,
                    quantity=1,
                )
            )
            session.flush()
        session.commit()
        clinic_id = clinic.id
        worker_ids = [worker.id for worker in workers]
        service_ids = [service.id for service in services]

    lock_barrier = threading.Barrier(2)
    start_barrier = threading.Barrier(2)
    connection_flag = f"resource-lock-{uuid.uuid4().hex}"

    def coordinate_first_resource_lock(
        connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        info = connection.info  # type: ignore[attr-defined]
        if (
            "FROM clinic_resources" not in statement
            or "FOR UPDATE" not in statement
            or info.get(connection_flag)
        ):
            return
        info[connection_flag] = True
        with suppress(threading.BrokenBarrierError):
            lock_barrier.wait(timeout=1.5)

    created: list[uuid.UUID] = []
    errors: list[Exception] = []
    outcome_lock = threading.Lock()

    def book(index: int) -> None:
        try:
            start_barrier.wait(timeout=3)
            with factory() as session:
                appointment = create_appointment_transactional(
                    session,
                    _calendar_client(),
                    clinic_id=clinic_id,
                    worker_id=worker_ids[index],
                    service_id=service_ids[index],
                    patient_name=f"Paciente {index}",
                    patient_phone=f"+3460000010{index}",
                    reason=None,
                    start_at=START_AT,
                    end_at=END_AT,
                    call_session_id=None,
                )
                with outcome_lock:
                    created.append(appointment.id)
        except Exception as exc:
            with outcome_lock:
                errors.append(exc)

    event.listen(
        database_engine, "after_cursor_execute", coordinate_first_resource_lock
    )
    threads = [threading.Thread(target=book, args=(index,)) for index in (0, 1)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        event.remove(
            database_engine,
            "after_cursor_execute",
            coordinate_first_resource_lock,
        )

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(created) == 2


def test_concurrent_idempotency_returns_the_committed_appointment(
    database_engine: Engine,
) -> None:
    if database_engine.dialect.name != "postgresql":
        pytest.skip("Concurrent row-lock semantics require PostgreSQL.")

    factory = sessionmaker(
        bind=database_engine,
        class_=Session,
        expire_on_commit=False,
    )
    with factory() as session:
        clinic, worker, service = _domain(session)
        clinic_id = clinic.id
        worker_id = worker.id
        service_id = service.id

    lookup_barrier = threading.Barrier(2)
    start_barrier = threading.Barrier(2)
    connection_flag = f"idempotency-lookup-{uuid.uuid4().hex}"

    def coordinate_initial_lookup(
        connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        info = connection.info  # type: ignore[attr-defined]
        if "appointments.idempotency_key =" not in statement or info.get(
            connection_flag
        ):
            return
        info[connection_flag] = True
        lookup_barrier.wait(timeout=3)

    created: list[uuid.UUID] = []
    errors: list[Exception] = []
    outcome_lock = threading.Lock()

    def book() -> None:
        try:
            start_barrier.wait(timeout=3)
            with factory() as session:
                appointment = create_appointment_transactional(
                    session,
                    _calendar_client(),
                    clinic_id=clinic_id,
                    worker_id=worker_id,
                    service_id=service_id,
                    patient_name="Paciente Idempotente",
                    patient_phone="+34600000111",
                    reason=None,
                    start_at=START_AT,
                    end_at=END_AT,
                    call_session_id=None,
                    idempotency_key="same-call:same-tool-call",
                )
                with outcome_lock:
                    created.append(appointment.id)
        except Exception as exc:
            with outcome_lock:
                errors.append(exc)

    event.listen(database_engine, "after_cursor_execute", coordinate_initial_lookup)
    threads = [threading.Thread(target=book) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        event.remove(database_engine, "after_cursor_execute", coordinate_initial_lookup)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(created) == 2
    assert len(set(created)) == 1
