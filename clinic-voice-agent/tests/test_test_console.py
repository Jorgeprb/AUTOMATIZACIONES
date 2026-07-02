"""Browser test-console API integration tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.admin import test_console as test_console_api
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
    CallSession,
    CallStatus,
    Clinic,
    Service,
    Worker,
)
from app.models import TestSession as SessionRecord
from app.test_console import TestConsoleError as ConsoleError

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
async def test_console_proposes_slots_and_books_after_natural_selection(
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
        selected_body = selected.json()
        assert selected_body["state"]["phase"] == "booked"
        assert selected_body["state"]["appointment_confirmed"] is True
        assert any(
            trace["name"] == "create_appointment"
            for trace in selected_body["tool_calls"]
        )

        loaded = await client.get(
            f"/api/admin/test-sessions/{started['id']}",
            headers=ADMIN_HEADERS,
        )
        assert loaded.status_code == 200
        assert "Consulta general" in loaded.json()["prompt"]

    with _factory(database_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Appointment)) == 1


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


@pytest.mark.anyio
async def test_console_openai_overrides_wrong_model_clinic_id(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI tool calls must use the TestSession clinic, not model IDs."""
    clinic, config = _domain(db_session)

    class FunctionCall:
        type = "function_call"
        name = "get_clinic_info"
        arguments = (
            '{"clinic_id":"00000000-0000-0000-0000-000000000000"}'
        )
        call_id = "call-tool-1"

    responses = iter(
        [
            SimpleNamespace(
                output=[FunctionCall()],
                output_text="",
            ),
            SimpleNamespace(
                output=[],
                output_text="He consultado la clínica real.",
            ),
        ]
    )

    def create_response(**kwargs: object) -> object:
        if "clinic_id real" not in str(kwargs["instructions"]):
            raise AssertionError("Prompt de test sin contexto técnico real.")
        return next(responses)

    monkeypatch.setattr(
        "app.test_console.OpenAI",
        lambda **_kwargs: SimpleNamespace(
            responses=SimpleNamespace(create=create_response)
        ),
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
            json={"message": "Dime información de la clínica"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_calls"][0]["name"] == "get_clinic_info"
    assert body["tool_calls"][0]["result"]["ok"] is True
    assert body["tool_calls"][0]["result"]["id"] == str(clinic.id)
    assert "clinic_id real" in body["prompt"]


@pytest.mark.anyio
async def test_console_openai_rejects_fake_worker_id_with_clear_tool_error(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI mode must not continue with invented worker IDs."""
    clinic, config = _domain(db_session)

    class FunctionCall:
        type = "function_call"
        name = "check_availability"
        arguments = (
            '{"worker_id":"f1b2d3c4-5678-4abc-9def-1234567890ab",'
            '"service_name":"Consulta general",'
            '"start_at":"2026-06-22T09:00:00+02:00",'
            '"end_at":"2026-06-22T09:30:00+02:00"}'
        )
        call_id = "call-tool-fake-worker"

    responses = iter(
        [
            SimpleNamespace(
                output=[FunctionCall()],
                output_text="",
            ),
            SimpleNamespace(
                output=[],
                output_text="Necesito usar un trabajador válido.",
            ),
        ]
    )

    def create_response(**kwargs: object) -> object:
        instructions = str(kwargs["instructions"])
        if "worker_id real" not in instructions:
            raise AssertionError("Prompt de test sin worker_id real.")
        if "No inventes worker_id ni service_id" not in instructions:
            raise AssertionError("Prompt sin regla anti IDs inventados.")
        return next(responses)

    monkeypatch.setattr(
        "app.test_console.OpenAI",
        lambda **_kwargs: SimpleNamespace(
            responses=SimpleNamespace(create=create_response)
        ),
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
            json={"message": "Quiero una cita mañana por la mañana"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    tool_result = body["tool_calls"][0]["result"]
    assert tool_result["ok"] is False
    assert tool_result["error"] == "RealtimeToolError"
    assert "worker_id no pertenece" in tool_result["message"]
    assert "Ana" in tool_result["message"]


@pytest.mark.anyio
async def test_console_warns_when_worker_has_no_calendar(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """The test UI payload should explain missing worker calendar setup."""
    clinic, config = _domain(db_session)
    worker = db_session.scalar(select(Worker).where(Worker.clinic_id == clinic.id))
    assert worker is not None
    db_session.execute(
        update(Worker)
        .where(Worker.id == worker.id)
        .values(calendar_id=None)
    )
    db_session.commit()
    with _factory(database_engine)() as check_session:
        stored_calendar_id = check_session.scalar(
            select(Worker.calendar_id).where(Worker.id == worker.id)
        )
        assert stored_calendar_id is None

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        started = await _start(client, clinic, config)

    assert "sin calendar_id" in started["prompt"]
    assert any("calendar_id" in warning for warning in started["warnings"]), started[
        "warnings"
    ]


@pytest.mark.anyio
async def test_console_close_marks_call_completed_and_blocks_messages(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Finalizar chat should close the test session and simulated call."""
    clinic, config = _domain(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        started = await _start(client, clinic, config)
        closed_response = await client.post(
            f"/api/admin/test-sessions/{started['id']}/close",
            headers=ADMIN_HEADERS,
        )
        assert closed_response.status_code == 200, closed_response.text
        closed = closed_response.json()
        assert closed["is_closed"] is True

        blocked = await client.post(
            f"/api/admin/test-sessions/{started['id']}/message",
            headers=ADMIN_HEADERS,
            json={"message": "Hola otra vez"},
        )
        assert blocked.status_code == 400
        assert "finalizado" in blocked.text

    with _factory(database_engine)() as session:
        stored = session.get(SessionRecord, started["id"])
        assert stored is not None
        call_id = stored.state_json["call_session_id"]
        call = session.get(CallSession, call_id)
        assert call is not None
        assert call.status == CallStatus.COMPLETED
        assert call.ended_at is not None
        event_count = session.scalar(
            select(func.count())
            .select_from(CallEvent)
            .where(CallEvent.event_type == "test_console.closed")
        )
        assert event_count == 1


@pytest.mark.anyio
async def test_console_tts_uses_selected_session_and_blocks_after_close(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The browser TTS endpoint should return finite audio and respect closure."""
    clinic, config = _domain(db_session)
    calls: list[str] = []

    def fake_tts(
        session: Session,
        settings: object,
        test_session: SessionRecord,
        text: str,
    ) -> bytes:
        del session, settings
        if test_session.state_json.get("closed"):
            raise ConsoleError("El chat de prueba ya está finalizado.")
        calls.append(text)
        return b"mp3-bytes"

    monkeypatch.setattr(test_console_api, "synthesize_test_session_audio", fake_tts)
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        started = await _start(client, clinic, config)
        audio = await client.post(
            f"/api/admin/test-sessions/{started['id']}/tts",
            headers=ADMIN_HEADERS,
            json={"text": "Hola desde el bot"},
        )
        assert audio.status_code == 200
        assert audio.headers["content-type"].startswith("audio/mpeg")
        assert audio.content == b"mp3-bytes"
        assert calls == ["Hola desde el bot"]

        await client.post(
            f"/api/admin/test-sessions/{started['id']}/close",
            headers=ADMIN_HEADERS,
        )
        blocked = await client.post(
            f"/api/admin/test-sessions/{started['id']}/tts",
            headers=ADMIN_HEADERS,
            json={"text": "No debe sonar"},
        )
        assert blocked.status_code == 400
