"""Incoming SIP webhook and Realtime control-event tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient, ConnectError, Request
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import get_db
from app.main import create_app
from app.models import (
    AssistantConfig,
    CallEvent,
    CallSession,
    CallStatus,
    Clinic,
    KnowledgeCategory,
    KnowledgeItem,
    PhoneNumber,
    PhoneProvider,
    Service,
    Worker,
)
from app.openai_realtime import events as realtime_events
from app.openai_realtime import webhook
from app.openai_realtime.events import RealtimeEventProcessor

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, Any]:
    """Load one documented-shape Realtime event fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _webhook_headers(body: bytes, *, valid: bool) -> dict[str, str]:
    """Build a real signature accepted by the OpenAI SDK verifier."""
    webhook_id = f"wh_test_{uuid.uuid4().hex}"
    timestamp = str(int(time.time()))
    signed_payload = f"{webhook_id}.{timestamp}.{body.decode('utf-8')}"
    signature = base64.b64encode(
        hmac.new(
            b"test-webhook-secret",
            signed_payload.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    if not valid:
        signature = base64.b64encode(b"invalid-signature").decode()
    return {
        "content-type": "application/json",
        "webhook-id": webhook_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": f"v1,{signature}",
    }


def _session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build sessions for request overrides and background event work."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _override_db(
    factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    """Yield one request-scoped test database session."""
    with factory() as session:
        yield session


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    """Return a FastAPI-compatible database dependency override."""

    def override() -> Generator[Session, None, None]:
        yield from _override_db(factory)

    return override


@pytest.mark.anyio
async def test_webhook_with_invalid_signature_returns_400(
    database_engine: Engine,
) -> None:
    """An SDK signature rejection must stop webhook processing."""
    factory = _session_factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    body = b"{}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/webhooks/openai/realtime",
            content=body,
            headers=_webhook_headers(body, valid=False),
        )

    assert response.status_code == 400
    with factory() as session:
        assert session.scalar(select(CallSession)) is None


@pytest.mark.anyio
async def test_openai_send_test_event_returns_200_without_accepting(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI's dashboard test event has data.id but no data.call_id."""
    factory = _session_factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    accept_mock = AsyncMock()
    control_mock = MagicMock()
    monkeypatch.setattr(webhook, "accept_realtime_call", accept_mock)
    monkeypatch.setattr(webhook, "start_call_control_task", control_mock)
    body = json.dumps(
        {
            "type": "realtime.call.incoming",
            "data": {"id": "rsstarted-abc123"},
        },
        separators=(",", ":"),
    ).encode()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/webhooks/openai/realtime",
            content=body,
            headers=_webhook_headers(body, valid=True),
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "test_event": True}
    accept_mock.assert_not_awaited()
    control_mock.assert_not_called()
    with factory() as session:
        assert session.scalar(select(CallSession)) is None


@pytest.mark.anyio
async def test_valid_incoming_webhook_creates_and_accepts_call(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid incoming event must persist SIP data and accept with tools."""
    clinic = Clinic(
        name="Clínica SIP",
        timezone="Europe/Madrid",
        phone_number="+34919999999",
    )
    phone_number = PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number="+34919999999",
        label="Principal",
    )
    assistant_config = AssistantConfig(
        clinic=clinic,
        name="Config SIP",
        realtime_model="gpt-realtime-clinic-test",
        realtime_voice="cedar",
        language="es",
        first_message="Hola desde la Clínica SIP.",
        system_prompt="Gestiona las citas de esta clínica.",
        safety_prompt="No des consejo médico.",
        booking_policy_prompt="Confirma antes de reservar.",
        cancellation_policy_prompt="Confirma antes de cancelar.",
        transfer_policy_prompt="Transfiere si se solicita.",
        transcript_enabled=True,
        recording_enabled=True,
        conversation_retention_days=20,
        is_active=True,
    )
    worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@sip.test",
        working_hours_json={},
    )
    service = Service(
        clinic=clinic,
        name="Consulta SIP",
        public_name="Consulta SIP",
        price_text="55 €",
        duration_minutes=30,
    )
    knowledge = KnowledgeItem(
        clinic=clinic,
        title="Ubicación SIP",
        category=KnowledgeCategory.LOCATION,
        content="Estamos junto a la plaza.",
    )
    db_session.add_all(
        [
            clinic,
            phone_number,
            assistant_config,
            worker,
            service,
            knowledge,
        ]
    )
    db_session.commit()
    incoming = _fixture("realtime_call_incoming.json")
    body = json.dumps(incoming, separators=(",", ":")).encode()
    accept_mock = AsyncMock(
        side_effect=[
            ConnectError("transient", request=Request("POST", "https://example.test")),
            None,
        ]
    )
    control_mock = MagicMock()
    monkeypatch.setattr(webhook, "accept_realtime_call", accept_mock)
    monkeypatch.setattr(webhook, "start_call_control_task", control_mock)

    factory = _session_factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        failed = await client.post(
            "/webhooks/openai/realtime",
            content=body,
            headers=_webhook_headers(body, valid=True),
        )
        assert failed.status_code == 502
        response = await client.post(
            "/webhooks/openai/realtime",
            content=body,
            headers=_webhook_headers(body, valid=True),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert accept_mock.await_count == 2
    assert accept_mock.await_args is not None
    accept_kwargs = accept_mock.await_args.kwargs
    assert accept_kwargs["call_id"] == incoming["data"]["call_id"]
    payload = accept_kwargs["payload"]
    assert payload["type"] == "realtime"
    assert payload["model"] == "gpt-realtime-clinic-test"
    assert payload["audio"]["output"]["voice"] == "cedar"
    assert payload["audio"]["input"]["transcription"]["language"] == "es"
    assert "Consulta SIP" in payload["instructions"]
    assert "55 €" in payload["instructions"]
    assert "Ubicación SIP" in payload["instructions"]
    assert {tool["name"] for tool in payload["tools"]} == {
        "get_clinic_info",
        "propose_slots",
        "check_availability",
        "create_appointment",
        "cancel_appointment",
        "transfer_to_human",
        "end_call",
    }

    with factory() as session:
        call = session.scalar(
            select(CallSession).where(
                CallSession.openai_call_id == incoming["data"]["call_id"]
            )
        )
        assert call is not None
        assert call.caller_phone == "+34600111222"
        assert call.called_number == "+34919999999"
        assert call.provider_call_id == "provider-call-test-001"
        assert call.clinic_id == clinic.id
        assert call.phone_number_id == phone_number.id
        assert call.assistant_config_id == assistant_config.id
        assert call.transcript_enabled is True
        assert call.recording_enabled is True
        assert call.status is CallStatus.INCOMING
        assert call.conversation_state_json["clinic_id"] == str(clinic.id)
        stored_event = session.scalar(
            select(CallEvent).where(CallEvent.call_session_id == call.id)
        )
        assert stored_event is not None
        assert stored_event.payload_json == incoming

    control_mock.assert_called_once()
    assert control_mock.call_args.kwargs["initial_message"] == (
        "Hola desde la Clínica SIP."
    )
    assert control_mock.call_args.kwargs["transcription_enabled"] is True


@pytest.mark.anyio
async def test_incoming_webhook_with_unknown_number_is_controlled(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown called number must never be accepted or assigned by fallback."""
    incoming = _fixture("realtime_call_incoming.json")
    incoming["data"]["call_id"] = "rtc_unknown_number"
    incoming["data"]["sip_headers"][1]["value"] = "sip:+34918880000@sip.api.openai.com"
    body = json.dumps(incoming, separators=(",", ":")).encode()
    accept_mock = AsyncMock()
    monkeypatch.setattr(webhook, "accept_realtime_call", accept_mock)

    factory = _session_factory(database_engine)
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/webhooks/openai/realtime",
            content=body,
            headers=_webhook_headers(body, valid=True),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == ("No active clinic matches the called number.")
    accept_mock.assert_not_awaited()
    with factory() as session:
        assert (
            session.scalar(
                select(CallSession).where(
                    CallSession.openai_call_id == "rtc_unknown_number"
                )
            )
            is None
        )


def _call_domain(session: Session) -> tuple[Clinic, CallSession]:
    """Create one clinic and one persisted Realtime call."""
    clinic = Clinic(
        name=f"Clínica Tool {uuid.uuid4()}",
        timezone="Europe/Madrid",
        phone_number=f"+34{uuid.uuid4().int % 10_000_000_000:010d}",
    )
    call = CallSession(
        openai_call_id=f"rtc_{uuid.uuid4().hex}",
        caller_phone="+34600111222",
        called_number=clinic.phone_number,
        status=CallStatus.ACTIVE,
        conversation_state_json={"clinic_id": str(clinic.id)},
    )
    session.add_all([clinic, call])
    session.commit()
    return clinic, call


@pytest.mark.anyio
async def test_websocket_event_processes_propose_slots_tool_call(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed function call must return slots and request model speech."""
    clinic, call = _call_domain(db_session)
    proposed_slot = {
        "worker_id": str(uuid.uuid4()),
        "worker_name": "Ana",
        "start_at": "2026-06-23T09:00:00+02:00",
        "end_at": "2026-06-23T09:30:00+02:00",
    }
    execute_mock = MagicMock(return_value={"ok": True, "slots": [proposed_slot]})
    monkeypatch.setattr(
        realtime_events,
        "execute_realtime_tool",
        execute_mock,
    )
    processor = RealtimeEventProcessor(
        settings=Settings(_env_file=None),
        session_factory=_session_factory(database_engine),
        call_session_id=call.id,
        clinic_id=clinic.id,
        openai_call_id=call.openai_call_id,
    )
    send_event = AsyncMock()

    await processor.handle_event(
        _fixture("realtime_tool_call_propose_slots.json"),
        send_event,
    )

    assert send_event.await_count == 2
    output_event = send_event.await_args_list[0].args[0]
    assert output_event["type"] == "conversation.item.create"
    assert output_event["item"]["type"] == "function_call_output"
    output = json.loads(output_event["item"]["output"])
    assert output == {"ok": True, "slots": [proposed_slot]}
    assert send_event.await_args_list[1].args[0] == {"type": "response.create"}
    assert execute_mock.call_args.args[0] == "propose_slots"


@pytest.mark.anyio
async def test_websocket_create_appointment_returns_confirmation(
    db_session: Session,
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A simulated booking tool result must be returned to the model."""
    clinic, call = _call_domain(db_session)
    confirmation = {
        "ok": True,
        "status": "confirmed",
        "appointment_id": str(uuid.uuid4()),
        "patient_name": "Eva",
    }
    execute_mock = MagicMock(return_value=confirmation)
    monkeypatch.setattr(
        realtime_events,
        "execute_realtime_tool",
        execute_mock,
    )
    processor = RealtimeEventProcessor(
        settings=Settings(_env_file=None),
        session_factory=_session_factory(database_engine),
        call_session_id=call.id,
        clinic_id=clinic.id,
        openai_call_id=call.openai_call_id,
    )
    send_event = AsyncMock()

    await processor.handle_event(
        _fixture("realtime_tool_call_create_appointment.json"),
        send_event,
    )

    output_event = send_event.await_args_list[0].args[0]
    assert json.loads(output_event["item"]["output"]) == confirmation
    assert execute_mock.call_args.args[0] == "create_appointment"


@pytest.mark.anyio
async def test_finalization_saves_transcript_and_summary(
    db_session: Session,
    database_engine: Engine,
) -> None:
    """Completed transcript events must survive WebSocket closure."""
    clinic, call = _call_domain(db_session)
    processor = RealtimeEventProcessor(
        settings=Settings(_env_file=None),
        session_factory=_session_factory(database_engine),
        call_session_id=call.id,
        clinic_id=clinic.id,
        openai_call_id=call.openai_call_id,
    )
    send_event = AsyncMock()
    await processor.handle_event(
        {
            "type": ("conversation.item.input_audio_transcription.completed"),
            "transcript": "Quiero una cita mañana.",
        },
        send_event,
    )
    await processor.handle_event(
        {
            "type": "response.output_audio_transcript.done",
            "transcript": "Claro. Voy a buscar horarios.",
        },
        send_event,
    )
    await processor.finalize(
        status=CallStatus.COMPLETED,
        summary="Paciente pidió una cita.",
    )

    with _session_factory(database_engine)() as session:
        persisted = session.get(CallSession, call.id)
        assert persisted is not None
        assert persisted.transcript_text is not None
        assert "Paciente: Quiero una cita mañana." in persisted.transcript_text
        assert "Asistente: Claro. Voy a buscar horarios." in persisted.transcript_text
        assert persisted.summary_text == "Paciente pidió una cita."
        assert persisted.status is CallStatus.COMPLETED
        assert persisted.ended_at is not None
