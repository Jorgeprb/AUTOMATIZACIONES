"""End-to-end local simulation tests without SIP or OpenAI."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.calendar.fake_client import InMemoryCalendarBackend
from app.config import Settings
from app.db import get_db
from app.main import create_app
from app.models import (
    Appointment,
    AppointmentStatus,
    CallEvent,
    Clinic,
    Service,
    Worker,
)
from app.simulation import SimulationEngine

MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 6, 21, 10, 0, tzinfo=MADRID)
TOMORROW = date(2026, 6, 22)
PATIENT_PHONE = "+34600123456"


def _factory(engine: Engine) -> sessionmaker[Session]:
    """Create non-expiring sessions for simulator tests."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _working_hours() -> dict[str, list[dict[str, str]]]:
    """Give both demo workers a stable morning every day."""
    return {
        day: [{"start": "09:00", "end": "12:00"}]
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    }


def _domain(session: Session) -> tuple[Clinic, Worker, Worker, Service]:
    """Persist the clinic, Ana, Luis, and general consultation service."""
    clinic = Clinic(
        name="Clínica Simulación",
        timezone="Europe/Madrid",
        phone_number="+34918887766",
    )
    ana = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@simulation.local",
        color_id="2",
        working_hours_json=_working_hours(),
    )
    luis = Worker(
        clinic=clinic,
        name="Luis",
        role="Médico",
        calendar_id="luis@simulation.local",
        color_id="7",
        working_hours_json=_working_hours(),
    )
    service = Service(
        clinic=clinic,
        name="Consulta general",
        duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
    )
    session.add_all([clinic, ana, luis, service])
    session.commit()
    return clinic, ana, luis, service


def _simulator(
    database_engine: Engine,
) -> tuple[SimulationEngine, InMemoryCalendarBackend]:
    """Create one isolated fake-calendar simulator."""
    backend = InMemoryCalendarBackend()
    simulator = SimulationEngine(
        settings=Settings(_env_file=None),
        session_factory=_factory(database_engine),
        mode="no-google",
        fake_backend=backend,
        now=NOW,
    )
    return simulator, backend


def _appointment_request(worker_name: str = "Ana") -> str:
    """Return a complete natural-language appointment request."""
    return (
        f"Quiero una cita con {worker_name} mañana por la mañana. "
        f"Me llamo Marta y mi teléfono es {PATIENT_PHONE}."
    )


def _book_first_slot(
    simulator: SimulationEngine,
    clinic: Clinic,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Run request and natural slot selection."""
    first = simulator.turn(_appointment_request(), clinic_id=clinic.id)
    assert first.action == "slots_proposed"
    confirmed = simulator.turn(
        "Elijo la primera opción",
        call_session_id=first.call_session_id,
    )
    assert confirmed.action == "appointment_created"
    return first.call_session_id, uuid.UUID(
        str(confirmed.tool_calls[-1]["result"]["appointment_id"])
    )


def test_create_appointment_with_ana_tomorrow_morning(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """A full simulated dialogue should create Ana's appointment."""
    clinic, ana, _, _ = _domain(db_session)
    simulator, backend = _simulator(database_engine)

    first = simulator.turn(_appointment_request(), clinic_id=clinic.id)

    assert first.action == "slots_proposed"
    assert first.proposed_slots
    assert first.proposed_slots[0].worker_name == "Ana"
    assert first.proposed_slots[0].start_at.date() == TOMORROW

    selected = simulator.turn(
        "Elijo la primera",
        call_session_id=first.call_session_id,
    )

    assert selected.action == "appointment_created"
    with _factory(database_engine)() as session:
        appointment = session.scalar(select(Appointment))
        assert appointment is not None
        assert appointment.worker_id == ana.id
        assert appointment.status is AppointmentStatus.CONFIRMED
        assert appointment.start_at.astimezone(MADRID).date() == TOMORROW
        assert appointment.call_session_id == first.call_session_id
        event_count = session.scalar(select(func.count()).select_from(CallEvent))
        assert event_count is not None
        assert event_count >= 5
    assert ana.calendar_id is not None
    assert len(backend.list_events(ana.calendar_id)) == 1


def test_when_ana_is_busy_simulator_proposes_luis(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """The simulator should fall back to Luis on the requested day."""
    clinic, ana, _, _ = _domain(db_session)
    simulator, backend = _simulator(database_engine)
    backend.add_busy(
        str(ana.calendar_id),
        start_at=datetime.combine(TOMORROW, time(9, 0), MADRID),
        end_at=datetime.combine(TOMORROW, time(12, 0), MADRID),
    )

    result = simulator.turn(_appointment_request(), clinic_id=clinic.id)

    assert result.action == "slots_proposed"
    assert result.proposed_slots
    assert result.proposed_slots[0].worker_name == "Luis"
    assert result.proposed_slots[0].start_at.date() == TOMORROW


def test_when_both_are_busy_simulator_proposes_another_day(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """A fully busy preferred day should move to the next real free day."""
    clinic, ana, luis, _ = _domain(db_session)
    simulator, backend = _simulator(database_engine)
    for worker in (ana, luis):
        backend.add_busy(
            str(worker.calendar_id),
            start_at=datetime.combine(TOMORROW, time(9, 0), MADRID),
            end_at=datetime.combine(TOMORROW, time(12, 0), MADRID),
        )

    result = simulator.turn(_appointment_request(), clinic_id=clinic.id)

    assert result.action == "slots_proposed"
    assert result.proposed_slots
    assert result.proposed_slots[0].start_at.date() > TOMORROW


def test_simulator_books_after_natural_time_choice_and_patient_data(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """A natural time acceptance plus missing data should create the booking."""
    clinic, _, _, _ = _domain(db_session)
    simulator, _ = _simulator(database_engine)
    first = simulator.turn(
        "Quiero cita mañana por la mañana",
        clinic_id=clinic.id,
    )
    assert first.action == "slots_proposed"

    selected = simulator.turn(
        "A las 9",
        call_session_id=first.call_session_id,
    )
    assert selected.action == "request_patient_data"
    assert selected.awaiting_confirmation

    confirmed = simulator.turn(
        "Soy Jorge y mi teléfono es 666123123",
        call_session_id=first.call_session_id,
    )

    assert confirmed.action == "appointment_created"
    assert "te reservo" in confirmed.reply
    with _factory(database_engine)() as session:
        appointment = session.scalar(select(Appointment))
        assert appointment is not None
        assert appointment.patient_name == "Jorge"
        assert appointment.patient_phone == "666123123"


def test_simulator_does_not_book_patient_data_without_slot_acceptance(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Patient data alone is not a slot acceptance."""
    clinic, _, _, _ = _domain(db_session)
    simulator, _ = _simulator(database_engine)
    first = simulator.turn(
        "Quiero cita mañana por la mañana",
        clinic_id=clinic.id,
    )

    result = simulator.turn(
        "Soy Jorge y mi teléfono es 666123123",
        call_session_id=first.call_session_id,
    )

    assert result.action == "request_slot_selection"
    with _factory(database_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0


def test_medical_emergency_recommends_112_and_does_not_book(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Emergency language must stop scheduling."""
    clinic, _, _, _ = _domain(db_session)
    simulator, _ = _simulator(database_engine)

    result = simulator.turn(
        "Tengo dolor fuerte y dificultad para respirar. Quiero una cita.",
        clinic_id=clinic.id,
    )

    assert result.action == "emergency"
    assert "112" in result.reply
    assert "urgencias" in result.reply.casefold()
    assert result.tool_calls == []
    with _factory(database_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0


def test_cancel_appointment_by_phone_and_date(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """The fake calendar and database should both process cancellation."""
    clinic, ana, _, _ = _domain(db_session)
    simulator, backend = _simulator(database_engine)
    call_session_id, appointment_id = _book_first_slot(simulator, clinic)

    result = simulator.turn(
        f"Cancela la cita del teléfono {PATIENT_PHONE} del {TOMORROW.isoformat()}",
        call_session_id=call_session_id,
    )

    assert result.action == "appointment_cancelled"
    with _factory(database_engine)() as session:
        appointment = session.get(Appointment, appointment_id)
        assert appointment is not None
        assert appointment.status is AppointmentStatus.CANCELLED
    assert ana.calendar_id is not None
    assert backend.list_events(ana.calendar_id) == []


@pytest.mark.anyio
async def test_dev_simulation_endpoint_runs_a_real_turn(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """The HTTP endpoint should create a simulated call and propose slots."""
    clinic, _, _, _ = _domain(db_session)
    factory = _factory(database_engine)
    app = create_app()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/dev/simulate-agent-turn",
            json={
                "clinic_id": str(clinic.id),
                "mode": "no-google",
                "now": NOW.isoformat(),
                "message": _appointment_request(),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "slots_proposed"
    assert body["call_session_id"]
    assert body["proposed_slots"][0]["worker_name"] == "Ana"
