"""Production routing, configuration, authentication, and privacy tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
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
from app.openai_realtime.events import RealtimeEventProcessor
from app.openai_realtime.session import build_session_config
from app.schemas import AgentCreateAppointmentRequest
from scripts.purge_calls import purge_expired_calls

INTERNAL_API_KEY = "test-internal-api-key-with-32-characters"


def _factory(engine: Engine) -> sessionmaker[Session]:
    """Create non-expiring test sessions."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _override_db(
    factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    """Yield one request-scoped database session."""
    with factory() as session:
        yield session


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    """Return a FastAPI-compatible database dependency override."""

    def override() -> Generator[Session, None, None]:
        yield from _override_db(factory)

    return override


def _production_settings() -> Settings:
    """Build valid production settings from the test environment."""
    return Settings(
        _env_file=None,
        app_environment="production",
        internal_api_key=INTERNAL_API_KEY,
        public_base_url="https://voice.test",
        google_redirect_uri="https://voice.test/auth/google/callback",
    )


def test_production_does_not_register_dev_routes() -> None:
    """Development simulation must not exist in production."""
    app = create_app(_production_settings())
    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/dev/simulate-agent-turn" not in paths
    assert "/docs" not in paths
    assert "/openapi.json" not in paths


def test_missing_production_internal_key_fails_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production startup must fail when a required secret is missing."""
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="INTERNAL_API_KEY"):
        Settings(
            _env_file=None,
            app_environment="production",
            internal_api_key=None,
            public_base_url="https://voice.test",
            google_redirect_uri="https://voice.test/auth/google/callback",
        )


def test_missing_production_admin_key_fails_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production startup must require a separate administration API key."""
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="ADMIN_API_KEY"):
        Settings(
            _env_file=None,
            app_environment="production",
            internal_api_key=INTERNAL_API_KEY,
            admin_api_key=None,
            public_base_url="https://voice.test",
            google_redirect_uri="https://voice.test/auth/google/callback",
        )


@pytest.mark.anyio
async def test_openai_webhook_without_signature_returns_400(
    database_engine: Engine,
) -> None:
    """Unsigned bodies must be rejected before call creation."""
    factory = _factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/webhooks/openai/realtime",
            json={"type": "realtime.call.incoming"},
        )

    assert response.status_code == 400
    with factory() as session:
        assert session.scalar(select(CallSession)) is None


@pytest.mark.anyio
async def test_internal_calendar_endpoint_requires_api_key(
    database_engine: Engine,
) -> None:
    """Calendar administration must not be publicly callable."""
    factory = _factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/calendar/status?clinic_id={uuid.uuid4()}",
        )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_public_webhook_has_basic_rate_limit(
    database_engine: Engine,
) -> None:
    """Repeated public requests should receive a stable 429 response."""
    factory = _factory(database_engine)
    settings = Settings(
        _env_file=None,
        webhook_rate_limit_per_minute=1,
    )
    app = create_app(settings)
    app.dependency_overrides[get_db] = _db_override(factory)
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/webhooks/openai/realtime",
            json={"type": "invalid"},
        )
        second = await client.post(
            "/webhooks/openai/realtime",
            json={"type": "invalid"},
        )

    assert first.status_code == 400
    assert second.status_code == 429
    assert second.headers["Retry-After"]


@pytest.mark.anyio
async def test_delete_call_session_cascades_events(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Authenticated deletion must remove the call and diagnostic events."""
    clinic = Clinic(
        name="Delete Clinic",
        timezone="Europe/Madrid",
        phone_number="+34911110001",
    )
    call = CallSession(
        clinic=clinic,
        openai_call_id="delete-call",
        caller_phone="+34600000001",
        called_number=clinic.phone_number,
        status=CallStatus.COMPLETED,
    )
    event = CallEvent(
        call_session=call,
        event_type="test",
        payload_json={"ok": True},
    )
    db_session.add_all([clinic, call, event])
    db_session.commit()

    factory = _factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.delete(
            f"/api/calls/{call.id}",
            headers={"X-Internal-API-Key": INTERNAL_API_KEY},
        )

    assert response.status_code == 200
    with factory() as session:
        assert session.get(CallSession, call.id) is None
        assert session.scalar(select(CallEvent)) is None


def test_purge_uses_clinic_retention_and_preserves_appointments(
    db_session: Session,
) -> None:
    """Purging old calls must keep appointments and clear their call link."""
    clinic = Clinic(
        name="Retention Clinic",
        timezone="Europe/Madrid",
        phone_number="+34911110002",
        data_retention_days=7,
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@retention.test",
        working_hours_json={},
    )
    service = Service(
        clinic=clinic,
        name="Consulta general",
        duration_minutes=30,
    )
    old_time = datetime.now(UTC) - timedelta(days=10)
    call = CallSession(
        clinic=clinic,
        openai_call_id="old-call",
        caller_phone="+34600000002",
        called_number=clinic.phone_number,
        status=CallStatus.COMPLETED,
        ended_at=old_time,
        created_at=old_time,
    )
    appointment = Appointment(
        clinic=clinic,
        worker=worker,
        service=service,
        call_session=call,
        google_calendar_id="ana@retention.test",
        google_event_id="retention-event",
        patient_name="Marta",
        patient_phone="+34600000002",
        reason="Consulta general",
        start_at=datetime.now(UTC) + timedelta(days=1),
        end_at=datetime.now(UTC) + timedelta(days=1, minutes=30),
    )
    db_session.add_all([clinic, worker, service, call, appointment])
    db_session.commit()

    result = purge_expired_calls(db_session, now=datetime.now(UTC))

    assert result.deleted == 1
    db_session.expire_all()
    persisted = db_session.get(Appointment, appointment.id)
    assert persisted is not None
    assert persisted.call_session_id is None


def test_purge_uses_assistant_config_retention_override(
    db_session: Session,
) -> None:
    """A call-linked config can define a shorter conversation retention."""
    clinic = Clinic(
        name="Config Retention Clinic",
        timezone="Europe/Madrid",
        phone_number="+34911110022",
        data_retention_days=30,
    )
    assistant_config = AssistantConfig(
        clinic=clinic,
        name="Privacidad corta",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es-ES",
        first_message="Hola.",
        system_prompt="Gestiona citas.",
        safety_prompt="No diagnostiques.",
        booking_policy_prompt="Confirma.",
        cancellation_policy_prompt="Confirma.",
        transfer_policy_prompt="Transfiere.",
        conversation_retention_days=5,
        is_active=True,
    )
    old_time = datetime.now(UTC) - timedelta(days=10)
    call = CallSession(
        clinic=clinic,
        assistant_config=assistant_config,
        openai_call_id="config-retention-call",
        caller_phone="+34600000022",
        called_number=clinic.phone_number,
        status=CallStatus.COMPLETED,
        ended_at=old_time,
        created_at=old_time,
    )
    db_session.add_all([clinic, assistant_config, call])
    db_session.commit()

    result = purge_expired_calls(db_session, now=datetime.now(UTC))

    assert result.deleted == 1
    assert db_session.get(CallSession, call.id) is None


def test_disabled_transcription_redacts_event_payload(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Disabled transcription must not persist spoken text."""
    clinic = Clinic(
        name="Private Clinic",
        timezone="Europe/Madrid",
        phone_number="+34911110003",
    )
    call = CallSession(
        clinic=clinic,
        openai_call_id="private-call",
        caller_phone="+34600000003",
        called_number=clinic.phone_number,
        status=CallStatus.ACTIVE,
    )
    db_session.add_all([clinic, call])
    db_session.commit()
    settings = Settings(_env_file=None, enable_call_transcription=False)
    processor = RealtimeEventProcessor(
        settings=settings,
        session_factory=_factory(database_engine),
        call_session_id=call.id,
        clinic_id=clinic.id,
        openai_call_id=call.openai_call_id,
    )

    processor._persist_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Texto sensible que no debe guardarse.",
        },
        client=False,
    )

    with _factory(database_engine)() as session:
        stored = session.scalar(select(CallEvent))
        assert stored is not None
        assert stored.payload_json["transcript_redacted"] is True
        assert "transcript" not in stored.payload_json


def test_disabled_transcription_is_omitted_from_realtime_session() -> None:
    """The accept payload must not request input transcription when disabled."""
    settings = Settings(_env_file=None, enable_call_transcription=False)

    payload = build_session_config(settings).as_accept_payload()

    assert "input" not in payload["audio"]


def test_detailed_appointment_reason_is_rejected() -> None:
    """The MVP should accept only a short general motive."""
    with pytest.raises(ValidationError, match="300"):
        AgentCreateAppointmentRequest(
            clinic_id=uuid.uuid4(),
            worker_id=uuid.uuid4(),
            patient_name="Marta",
            patient_phone="+34600000000",
            reason="x" * 301,
            start_at=datetime.now(UTC),
            end_at=datetime.now(UTC) + timedelta(minutes=30),
        )
