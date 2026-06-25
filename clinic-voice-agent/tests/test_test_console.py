"""Browser test-console API integration tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.calendar.fake_client import (
    FakeGoogleCalendarClient,
    InMemoryCalendarBackend,
)
from app.db import get_db
from app.main import create_app
from app.models import (
    Appointment,
    AssistantConfig,
    CallEvent,
    Clinic,
    Service,
    Worker,
)
from app.models import TestSession as SessionRecord

ADMIN_HEADERS = {
    "X-Admin-API-Key": "test-admin-api-key-with-32-characters",
}


def _factory(engine: Engine) -> sessionmaker[Session]:
    """Create non-expiring sessions for one isolated test schema."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _app(engine: Engine) -> FastAPI:
    """Create an application using the isolated test database."""
    factory = _factory(engine)
    app = create_app()

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    return app


def _working_hours() -> dict[str, list[dict[str, str]]]:
    """Provide deterministic broad hours for every weekday."""
    return {
        day: [{"start": "09:00", "end": "20:00"}]
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


def _domain(session: Session) -> tuple[Clinic, AssistantConfig]:
    """Create a complete clinic context for browser simulations."""
    clinic = Clinic(
        name="Clínica Console",
        timezone="Europe/Madrid",
        phone_number="+34910000991",
    )
    config = AssistantConfig(
        clinic=clinic,
        name="Prueba",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es",
        first_message="Hola. Soy el asistente virtual. ¿En qué puedo ayudarte?",
        system_prompt="Gestiona citas e información general.",
        safety_prompt="No diagnostiques.",
        booking_policy_prompt="Confirma antes de reservar.",
        cancellation_policy_prompt="Confirma la cancelación.",
        transfer_policy_prompt="Transfiere cuando no puedas ayudar.",
        is_active=True,
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@test-console.local",
        working_hours_json=_working_hours(),
    )
    service = Service(
        clinic=clinic,
        name="Consulta general",
        public_name="Consulta general",
        price_text="50 €",
        duration_minutes=30,
    )
    session.add_all([clinic, config, worker, service])
    session.commit()
    return clinic, config


async def _start(
    client: AsyncClient,
    clinic: Clinic,
    config: AssistantConfig,
    *,
    use_real_calendar: bool = False,
) -> dict[str, object]:
    """Start one simulator-backed browser session."""
    response = await client.post(
        f"/api/admin/clinics/{clinic.id}/test-sessions",
        headers=ADMIN_HEADERS,
        json={
            "assistant_config_id": str(config.id),
            "use_real_calendar": use_real_calendar,
            "engine": "simulator",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete_request() -> str:
    """Return a message with all data required to propose slots."""
    tomorrow = (
        datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=1)
    ).date()
    return (
        "Quiero una cita de Consulta general con Ana "
        f"el {tomorrow.isoformat()} por la mañana. "
        "Me llamo Marta y mi teléfono es +34600111222."
    )


@pytest.mark.anyio
async def test_console_proposes_slots_and_does_not_book_without_confirmation(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake mode must propose real scheduler slots without touching Google."""
    clinic, config = _domain(db_session)

    def unexpected_google(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Fake mode must not authorize Google.")

    monkeypatch.setattr(
        "app.simulation.get_authorized_calendar_client",
        unexpected_google,
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        started = await _start(client, clinic, config)
        response = await client.post(
            f"/api/admin/test-sessions/{started['id']}/message",
            headers=ADMIN_HEADERS,
            json={"message": _complete_request()},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tool_calls"][0]["name"] == "propose_slots"
        assert body["state"]["appointment_confirmed"] is False

        selected = await client.post(
            f"/api/admin/test-sessions/{started['id']}/message",
            headers=ADMIN_HEADERS,
            json={"message": "Elijo la primera opción"},
        )
        assert selected.status_code == 200
        assert selected.json()["state"]["phase"] == "awaiting_confirmation"

        loaded = await client.get(
            f"/api/admin/test-sessions/{started['id']}",
            headers=ADMIN_HEADERS,
        )
        assert loaded.status_code == 200
        assert "Consulta general" in loaded.json()["prompt"]

    with _factory(database_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0


@pytest.mark.anyio
async def test_console_real_calendar_uses_authorized_provider(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real-calendar mode must route scheduler calls through Google provider."""
    clinic, config = _domain(db_session)
    calls = 0
    client = FakeGoogleCalendarClient(InMemoryCalendarBackend())

    def authorized_provider(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return client

    monkeypatch.setattr(
        "app.simulation.get_authorized_calendar_client",
        authorized_provider,
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as http_client:
        started = await _start(
            http_client,
            clinic,
            config,
            use_real_calendar=True,
        )
        response = await http_client.post(
            f"/api/admin/test-sessions/{started['id']}/message",
            headers=ADMIN_HEADERS,
            json={"message": _complete_request()},
        )
    assert response.status_code == 200, response.text
    assert calls >= 1


@pytest.mark.anyio
async def test_console_emergency_never_calls_booking_tool(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Urgency language must stop all appointment creation."""
    clinic, config = _domain(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        started = await _start(client, clinic, config)
        response = await client.post(
            f"/api/admin/test-sessions/{started['id']}/message",
            headers=ADMIN_HEADERS,
            json={
                "message": (
                    "Tengo dolor fuerte y dificultad para respirar. "
                    "Quiero una cita."
                )
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "112" in body["messages"][-1]["content"]
        assert body["state"]["emergency_detected"] is True
        assert not any(
            trace["name"] == "create_appointment"
            for trace in body["tool_calls"]
        )

        deleted = await client.delete(
            f"/api/admin/test-sessions/{started['id']}",
            headers=ADMIN_HEADERS,
        )
        assert deleted.status_code == 200

    with _factory(database_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 0
        assert (
            session.scalar(select(func.count()).select_from(SessionRecord))
            == 0
        )
        booking_events = session.scalar(
            select(func.count())
            .select_from(CallEvent)
            .where(CallEvent.event_type == "simulation.tool_call")
        )
        assert booking_events == 0


@pytest.mark.anyio
async def test_console_can_use_configured_openai_text_engine(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI mode should use the Responses client without SIP."""
    clinic, config = _domain(db_session)
    responses = SimpleNamespace(
        create=lambda **_kwargs: SimpleNamespace(
            output=[],
            output_text="Respuesta desde el modelo de prueba.",
        )
    )
    monkeypatch.setattr(
        "app.test_console.OpenAI",
        lambda **_kwargs: SimpleNamespace(responses=responses),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        started_response = await client.post(
            f"/api/admin/clinics/{clinic.id}/test-sessions",
            headers=ADMIN_HEADERS,
            json={
                "assistant_config_id": str(config.id),
                "use_real_calendar": False,
                "engine": "openai",
            },
        )
        assert started_response.status_code == 201
        started = started_response.json()
        response = await client.post(
            f"/api/admin/test-sessions/{started['id']}/message",
            headers=ADMIN_HEADERS,
            json={"message": "Hola"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["engine"] == "openai"
    assert response.json()["messages"][-1]["content"] == (
        "Respuesta desde el modelo de prueba."
    )
