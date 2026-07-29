"""Production setup checklist and dashboard API tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db
from app.main import create_app
from app.models import (
    Appointment,
    AppointmentSource,
    AppointmentStatus,
    AssistantConfig,
    CallEvent,
    CallOutcome,
    CallSession,
    CallStatus,
    Clinic,
    GoogleCredential,
    KnowledgeCategory,
    KnowledgeItem,
    PhoneNumber,
    PhoneProvider,
    Service,
    Worker,
)
from app.models import TestSession as SessionRecord
from scripts.seed_demo import seed_demo

ADMIN_HEADERS = {
    "X-Admin-API-Key": "test-admin-api-key-with-32-characters",
}


def _factory(engine: Engine) -> sessionmaker[Session]:
    """Create non-expiring sessions for one isolated schema."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    """Build one FastAPI database dependency override."""

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return override


def _app(engine: Engine) -> FastAPI:
    """Create an application using the isolated database."""
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(_factory(engine))
    return app


def _ready_clinic(session: Session) -> Clinic:
    """Persist a clinic with evidence for every setup step."""
    now = datetime.now(UTC)
    clinic = Clinic(
        name="Clínica Lista",
        legal_name="Clínica Lista, S.L.",
        timezone="Europe/Madrid",
        default_language="es",
        phone_number="+34910000888",
        address="Calle Lista 1, Madrid",
        website="https://lista.example.test",
        email="hola@lista.example.test",
        description="Clínica lista para pruebas.",
        opening_hours_json={"monday": [{"start": "09:00", "end": "18:00"}]},
        emergency_message="Llama al 112.",
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@lista.example.test",
        working_hours_json={"monday": [{"start": "09:00", "end": "18:00"}]},
    )
    service = Service(
        clinic=clinic,
        name="Consulta",
        public_name="Consulta",
        price_text="50 €",
        duration_minutes=30,
        is_bookable_by_bot=True,
    )
    config = AssistantConfig(
        clinic=clinic,
        name="Producción",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es",
        first_message="Hola. Soy el asistente virtual.",
        system_prompt="Gestiona citas.",
        safety_prompt="No diagnostiques.",
        booking_policy_prompt="Confirma antes de reservar.",
        cancellation_policy_prompt="Confirma antes de cancelar.",
        transfer_policy_prompt="Transfiere cuando sea necesario.",
        is_active=True,
    )
    phone = PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number=clinic.phone_number,
        label="Principal",
        sip_target="sip:proj_live_clinic@sip.api.openai.com;transport=tls",
        webhook_url="https://voice.clinica-lista.es/webhooks/openai/realtime",
    )
    credential = GoogleCredential(
        clinic=clinic,
        account_email="clinic@example.test",
        token_json_encrypted="encrypted",
    )
    knowledge = KnowledgeItem(
        clinic=clinic,
        title="Ubicación",
        category=KnowledgeCategory.LOCATION,
        content="Calle Lista 1.",
    )
    real_call = CallSession(
        clinic=clinic,
        phone_number=phone,
        assistant_config=config,
        openai_call_id="call_real_dashboard",
        caller_phone="+34600000888",
        called_number=clinic.phone_number,
        status=CallStatus.FAILED,
        outcome=CallOutcome.FAILED,
        started_at=now - timedelta(hours=1),
        ended_at=now - timedelta(minutes=55),
    )
    event = CallEvent(
        call_session=real_call,
        event_type="response.error",
        payload_json={"error": "test"},
    )
    appointment = Appointment(
        clinic=clinic,
        worker=worker,
        service=service,
        call_session=real_call,
        google_calendar_id=worker.calendar_id,
        google_event_id="dashboard-event",
        patient_name="Marta",
        patient_phone="+34600000888",
        start_at=now + timedelta(days=2),
        end_at=now + timedelta(days=2, minutes=30),
        status=AppointmentStatus.CONFIRMED,
        source=AppointmentSource.VOICE_BOT,
    )
    simulation = SessionRecord(
        clinic=clinic,
        assistant_config=config,
        messages_json=[
            {"role": "assistant", "content": "Hola"},
            {"role": "user", "content": "Quiero una cita"},
            {"role": "assistant", "content": "¿Qué día?"},
        ],
        state_json={},
    )
    session.add_all(
        [
            clinic,
            worker,
            service,
            config,
            phone,
            credential,
            knowledge,
            real_call,
            event,
            appointment,
            simulation,
        ]
    )
    session.commit()
    return clinic


@pytest.mark.anyio
async def test_setup_status_detects_incomplete_clinic(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """A bare clinic must expose blocking production steps."""
    clinic = Clinic(
        name="Clínica Incompleta",
        timezone="Europe/Madrid",
        phone_number="+34910000777",
    )
    db_session.add(clinic)
    db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/admin/clinics/{clinic.id}/setup-status",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is False
    assert body["blocking_errors"]
    assert not next(item for item in body["items"] if item["key"] == "google_calendar")[
        "completed"
    ]


@pytest.mark.anyio
async def test_setup_status_detects_ready_clinic(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """A fully evidenced setup must be marked ready."""
    clinic = _ready_clinic(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/admin/clinics/{clinic.id}/setup-status",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is True
    assert body["blocking_errors"] == []
    assert all(item["completed"] for item in body["items"])


@pytest.mark.anyio
async def test_dashboard_loads_with_demo_and_operational_data(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """The endpoint must aggregate useful cards from clinic data."""
    demo = seed_demo(
        db_session,
        clinic_name="Clínica Demo",
        clinic_timezone="Europe/Madrid",
        clinic_phone_number="+34910000666",
    )
    now = datetime.now(UTC)
    call = CallSession(
        clinic=demo.clinic,
        openai_call_id="call_demo_dashboard",
        caller_phone="+34600000666",
        called_number=demo.clinic.phone_number,
        status=CallStatus.COMPLETED,
        outcome=CallOutcome.NO_ACTION,
        started_at=now - timedelta(minutes=10),
        ended_at=now - timedelta(minutes=5),
    )
    appointment = Appointment(
        clinic=demo.clinic,
        worker=demo.workers[0],
        service=demo.services[0],
        google_calendar_id="demo-calendar",
        google_event_id="demo-dashboard-event",
        patient_name="Paciente Demo",
        patient_phone="+34600000666",
        start_at=now + timedelta(days=1),
        end_at=now + timedelta(days=1, minutes=30),
        status=AppointmentStatus.CONFIRMED,
        source=AppointmentSource.ADMIN_PANEL,
    )
    db_session.add_all([call, appointment])
    db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/admin/clinics/{demo.clinic.id}/dashboard",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_workers"] == 2
    assert body["bookable_services"] == 3
    assert body["calls_last_24h"] == 1
    assert body["upcoming_appointments"] == 1
    assert body["last_call"]["id"] == str(call.id)
