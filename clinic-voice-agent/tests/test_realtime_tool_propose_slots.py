"""Realtime propose_slots tool argument sanitization tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.calendar.fake_client import (
    FakeGoogleCalendarClient,
    InMemoryCalendarBackend,
)
from app.config import Settings
from app.models import CallSession, CallStatus, Clinic, Service, Worker
from app.openai_realtime.tools import ToolExecutionContext, execute_realtime_tool
from app.schemas import AgentProposeSlotsRequest

MADRID = ZoneInfo("Europe/Madrid")


def _session_factory(engine: Engine) -> Callable[[], Session]:
    """Create non-expiring sessions for the Realtime tool context."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _working_hours() -> dict[str, list[dict[str, str]]]:
    """Return broad Monday hours for deterministic slot generation."""
    return {
        "monday": [{"start": "09:00", "end": "14:00"}],
        "tuesday": [],
        "wednesday": [],
        "thursday": [],
        "friday": [],
        "saturday": [],
        "sunday": [],
    }


def _domain(session: Session) -> tuple[Clinic, Worker, Service, CallSession]:
    """Persist one clinic with a linked worker, one service, and one call."""
    clinic = Clinic(
        name="Clínica Tool Slots",
        timezone="Europe/Madrid",
        phone_number="+34910009901",
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@tool-slots.test",
        working_hours_json=_working_hours(),
    )
    service = Service(
        clinic=clinic,
        name="Consulta general",
        duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
    )
    call = CallSession(
        clinic=clinic,
        openai_call_id="rtc_tool_slots",
        caller_phone="+34600111222",
        called_number="+34910009901",
        status=CallStatus.ACTIVE,
        conversation_state_json={"mode": "test"},
    )
    session.add_all([clinic, worker, service, call])
    session.commit()
    return clinic, worker, service, call


def _context(
    engine: Engine,
    clinic: Clinic,
    call: CallSession,
    backend: InMemoryCalendarBackend,
) -> ToolExecutionContext:
    """Build a trusted Realtime execution context with fake calendar."""

    def calendar_provider(
        _session: Session,
        _settings: Settings,
        _clinic_id: object,
    ) -> FakeGoogleCalendarClient:
        return FakeGoogleCalendarClient(backend)

    return ToolExecutionContext(
        settings=Settings(_env_file=None),
        session_factory=_session_factory(engine),
        call_session_id=call.id,
        clinic_id=clinic.id,
        openai_call_id=call.openai_call_id,
        calendar_client_provider=calendar_provider,
        now=datetime(2026, 6, 21, 8, 0, tzinfo=MADRID),
    )


def _first_slot_duration(result: dict[str, object]) -> timedelta:
    """Read the visible appointment duration from the first returned slot."""
    slots = result["slots"]
    assert isinstance(slots, list)
    assert slots
    first_slot = slots[0]
    assert isinstance(first_slot, dict)
    start_at = datetime.fromisoformat(str(first_slot["start_at"]))
    end_at = datetime.fromisoformat(str(first_slot["end_at"]))
    return end_at - start_at


def test_propose_slots_tool_ignores_duration_when_service_id_is_present(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Model calls with both fields should use the configured service duration."""
    clinic, _worker, service, call = _domain(db_session)
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())

    result = execute_realtime_tool(
        "propose_slots",
        {
            "service_id": str(service.id),
            "duration_minutes": 999,
            "preferred_date": date(2026, 6, 22).isoformat(),
            "preferred_time_window": "morning",
            "max_slots": 1,
        },
        context,
    )

    assert result["ok"] is True
    assert _first_slot_duration(result) == timedelta(minutes=30)
    db_session.refresh(call)
    state = call.conversation_state_json
    assert state["intent"] == "create_appointment"
    assert state["awaiting_confirmation"] is True
    assert state["service"]["id"] == str(service.id)
    assert state["pending_slots"][0]["start_at"].startswith("2026-06-22T09:00")


def test_propose_slots_tool_allows_duration_when_service_id_is_missing(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Raw duration remains valid when no service has been selected yet."""
    clinic, _worker, _service, call = _domain(db_session)
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())

    result = execute_realtime_tool(
        "propose_slots",
        {
            "duration_minutes": 20,
            "preferred_date": date(2026, 6, 22).isoformat(),
            "preferred_time_window": "morning",
            "max_slots": 1,
        },
        context,
    )

    assert result["ok"] is True
    assert _first_slot_duration(result) == timedelta(minutes=20)


def test_propose_slots_tool_resolves_worker_and_service_names(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Names supplied by the model should resolve to real clinic IDs."""
    clinic, _worker, _service, call = _domain(db_session)
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())

    result = execute_realtime_tool(
        "propose_slots",
        {
            "service_name": "Consulta general",
            "worker_name": "Ana",
            "preferred_date": date(2026, 6, 22).isoformat(),
            "preferred_time_window": "morning",
            "max_slots": 1,
        },
        context,
    )

    assert result["ok"] is True
    assert _first_slot_duration(result) == timedelta(minutes=30)


def test_check_availability_rejects_fake_worker_id(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Fake or cross-clinic worker IDs should fail before calendar checks."""
    clinic, _worker, service, call = _domain(db_session)
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())
    start_at = datetime(2026, 6, 22, 9, 0, tzinfo=MADRID)

    result = execute_realtime_tool(
        "check_availability",
        {
            "worker_id": "f1b2d3c4-5678-4abc-9def-1234567890ab",
            "service_id": str(service.id),
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(minutes=30)).isoformat(),
        },
        context,
    )

    assert result["ok"] is False
    assert result["error"] == "RealtimeToolError"
    assert "worker_id no pertenece" in str(result["message"])
    assert "Ana" in str(result["message"])


def test_check_availability_auto_selects_single_calendar_worker(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """When there is one linked worker, the server can inject it safely."""
    clinic, _worker, service, call = _domain(db_session)
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())
    start_at = datetime(2026, 6, 22, 9, 0, tzinfo=MADRID)

    result = execute_realtime_tool(
        "check_availability",
        {
            "service_name": service.name,
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(minutes=30)).isoformat(),
        },
        context,
    )

    assert result["ok"] is True
    assert result["available"] is True


def test_create_appointment_resolves_worker_and_service_names(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """The OpenAI console can reserve using real names instead of IDs."""
    clinic, _worker, _service, call = _domain(db_session)
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())
    start_at = datetime(2026, 6, 22, 9, 0, tzinfo=MADRID)

    result = execute_realtime_tool(
        "create_appointment",
        {
            "worker_name": "Ana",
            "service_name": "Consulta general",
            "patient_name": "Paciente Uno",
            "patient_phone": "+34600000001",
            "reason": "Consulta general",
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(minutes=30)).isoformat(),
            "confirmed_by_caller": True,
        },
        context,
    )

    assert result["ok"] is True
    assert result["worker_name"] == "Ana"
    db_session.refresh(call)
    state = call.conversation_state_json
    assert state["appointment_id"] == result["appointment_id"]
    assert state["awaiting_confirmation"] is False
    assert state["patient_name"] == "Paciente Uno"


def test_propose_slots_without_worker_calendar_returns_clear_error(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Workers without calendar_id must not be offered for automatic booking."""
    clinic, worker, service, call = _domain(db_session)
    worker.calendar_id = None
    db_session.commit()
    context = _context(database_engine, clinic, call, InMemoryCalendarBackend())

    result = execute_realtime_tool(
        "propose_slots",
        {
            "service_id": str(service.id),
            "preferred_date": date(2026, 6, 22).isoformat(),
            "preferred_time_window": "morning",
            "max_slots": 1,
        },
        context,
    )

    assert result["ok"] is False
    assert "No hay trabajadores activos con calendar_id" in str(result["message"])


def test_manual_agent_propose_slots_request_still_rejects_both_fields() -> None:
    """Manual API payloads keep the strict exactly-one validation."""
    with pytest.raises(ValidationError):
        AgentProposeSlotsRequest.model_validate(
            {
                "clinic_id": uuid.uuid4(),
                "service_id": uuid.uuid4(),
                "duration_minutes": 30,
            }
        )
