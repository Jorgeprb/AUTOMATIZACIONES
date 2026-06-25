"""Persistence tests for the clinic domain models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentSource,
    AppointmentStatus,
    AssistantConfig,
    CallEvent,
    CallSession,
    CallStatus,
    Clinic,
    ConversationFlow,
    GoogleCredential,
    KnowledgeItem,
    PhoneNumber,
    Service,
    Worker,
)
from scripts.seed_demo import seed_demo


def test_create_complete_model_graph(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """All domain models should persist with relationships and defaults."""
    start_at = datetime.now(UTC) + timedelta(days=1)
    clinic = Clinic(
        name="Clínica Persistencia",
        timezone="Europe/Madrid",
        phone_number="+34910000001",
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@example.test",
        color_id="2",
        working_hours_json={"monday": [{"start": "09:00", "end": "17:00"}]},
    )
    service = Service(
        clinic=clinic,
        name="Consulta general",
        duration_minutes=30,
    )
    call_session = CallSession(
        openai_call_id="rtc_test_001",
        caller_phone="+34600000000",
        called_number=clinic.phone_number,
        conversation_state_json={"step": "collecting_patient_name"},
    )
    appointment = Appointment(
        clinic=clinic,
        worker=worker,
        service=service,
        call_session=call_session,
        google_calendar_id=worker.calendar_id,
        google_event_id="event-test-001",
        patient_name="Paciente Test",
        patient_phone="+34611111111",
        reason="Primera consulta",
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
    )
    event = CallEvent(
        call_session=call_session,
        event_type="realtime.call.incoming",
        payload_json={"call_id": "rtc_test_001"},
    )
    credential = GoogleCredential(
        clinic=clinic,
        account_email="clinic@example.test",
        token_json_encrypted="encrypted-test-token",
    )

    db_session.add_all(
        [
            clinic,
            worker,
            service,
            call_session,
            appointment,
            event,
            credential,
        ]
    )
    db_session.commit()

    persisted = db_session.scalar(
        select(Appointment).where(Appointment.id == appointment.id)
    )
    assert persisted is not None
    assert isinstance(persisted.id, uuid.UUID)
    assert persisted.status is AppointmentStatus.PENDING
    assert persisted.source is AppointmentSource.VOICE_BOT
    assert persisted.call_session is call_session
    assert call_session.status is CallStatus.INCOMING
    assert call_session.events == [event]
    assert clinic.created_at is not None
    assert clinic.updated_at is not None

    inspector = inspect(database_engine)
    appointment_indexes = {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("appointments")
    }
    call_indexes = {index["name"] for index in inspector.get_indexes("call_sessions")}
    appointment_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("appointments")
    }
    call_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("call_sessions")
    }

    assert appointment_indexes["ix_appointments_worker_schedule"] == [
        "worker_id",
        "start_at",
        "end_at",
    ]
    assert "ix_appointments_patient_phone" in appointment_indexes
    assert "ix_call_sessions_openai_call_id" in call_indexes
    assert "ck_appointments_appointment_status" in appointment_checks
    assert "ck_call_sessions_call_session_status" in call_checks


def test_database_rejects_invalid_status(db_session: Session) -> None:
    """Database check constraints should reject unsupported status values."""
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                """
                INSERT INTO call_sessions (
                    id,
                    openai_call_id,
                    caller_phone,
                    called_number,
                    status
                )
                VALUES (
                    :id,
                    :openai_call_id,
                    :caller_phone,
                    :called_number,
                    :status
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "openai_call_id": "rtc_invalid_status",
                "caller_phone": "+34600000000",
                "called_number": "+34910000000",
                "status": "unsupported",
            },
        )
    db_session.rollback()


def test_demo_seed_is_idempotent(db_session: Session) -> None:
    """The seed should create one clinic, two workers, and three services."""
    seed_kwargs = {
        "clinic_name": "Clínica Demo",
        "clinic_timezone": "Europe/Madrid",
        "clinic_phone_number": "+34910000002",
    }

    first = seed_demo(db_session, **seed_kwargs)
    second = seed_demo(db_session, **seed_kwargs)

    assert first.clinic.id == second.clinic.id
    assert {worker.name for worker in second.workers} == {"Ana", "Luis"}
    assert second.service.name == "Consulta general"
    assert second.service.duration_minutes == 30
    assert {service.name: service.duration_minutes for service in second.services} == {
        "Consulta general": 30,
        "Revisión": 45,
        "Urgencia no médica": 20,
    }
    assert db_session.scalar(select(func.count()).select_from(Clinic)) == 1
    assert db_session.scalar(select(func.count()).select_from(Worker)) == 2
    assert db_session.scalar(select(func.count()).select_from(Service)) == 3
    assert db_session.scalar(select(func.count()).select_from(PhoneNumber)) == 1
    assert db_session.scalar(select(func.count()).select_from(AssistantConfig)) == 1
    assert db_session.scalar(select(func.count()).select_from(KnowledgeItem)) == 4
    assert db_session.scalar(select(func.count()).select_from(ConversationFlow)) == 1
