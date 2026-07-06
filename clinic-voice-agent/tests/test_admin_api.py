"""End-to-end CRUD tests for the multi-clinic administration API."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import realtime_preview as realtime_preview_service
from app.api.admin import content as content_api
from app.api.admin import core as core_api
from app.api.admin import realtime_preview as realtime_preview_api
from app.db import get_db
from app.knowledge.importers import ExtractedKnowledge
from app.main import create_app
from app.models import (
    Appointment,
    AppointmentSource,
    AppointmentStatus,
    CallEvent,
    CallOutcome,
    CallSession,
    CallStatus,
    Clinic,
    KnowledgeItem,
    Service,
    Worker,
)
from app.voice_providers.base import TTSResult

ADMIN_KEY = "test-admin-api-key-with-32-characters"
ADMIN_HEADERS = {"X-Admin-API-Key": ADMIN_KEY}


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return override


def _app(engine: Engine) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_db] = _db_override(_factory(engine))
    return app


async def _create_clinic(client: AsyncClient, suffix: str = "") -> dict[str, object]:
    response = await client.post(
        "/api/admin/clinics",
        headers=ADMIN_HEADERS,
        json={
            "name": f"Clínica Panel {suffix}",
            "legal_name": "Clínica Panel, S.L.",
            "timezone": "Europe/Madrid",
            "default_language": "es",
            "main_phone_number": f"+3492{uuid.uuid4().int % 10_000_000_000:010d}",
            "address": "Calle Test 1",
            "website": "https://clinic.example.test",
            "email": "panel@clinic.example.test",
            "description": "Clínica para pruebas CRUD.",
            "opening_hours_json": {"monday": [{"start": "09:00", "end": "17:00"}]},
            "emergency_message": "Llama al 112.",
            "data_retention_days": 30,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.anyio
async def test_admin_api_requires_its_own_key(database_engine: Engine) -> None:
    """Admin routes must reject missing and internal-only credentials."""
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        missing = await client.get("/api/admin/clinics")
        internal = await client.get(
            "/api/admin/clinics",
            headers={
                "X-Internal-API-Key": ("test-internal-api-key-with-32-characters")
            },
        )

    assert missing.status_code == 401
    assert internal.status_code == 401

    schema = _app(database_engine).openapi()
    security_schemes = schema["components"]["securitySchemes"]
    assert security_schemes["AdminApiKey"]["name"] == "X-Admin-API-Key"


@pytest.mark.anyio
async def test_clinic_worker_service_and_phone_crud(
    database_engine: Engine,
) -> None:
    """Main frontend resources should support create, list, update, and delete."""
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Principal")
        clinic_id = clinic["id"]

        invalid_timezone = await client.patch(
            f"/api/admin/clinics/{clinic_id}",
            headers=ADMIN_HEADERS,
            json={"timezone": "Mars/Olympus"},
        )
        assert invalid_timezone.status_code == 422

        listed = await client.get(
            "/api/admin/clinics?page=1&page_size=10&is_active=true",
            headers=ADMIN_HEADERS,
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        updated = await client.patch(
            f"/api/admin/clinics/{clinic_id}",
            headers=ADMIN_HEADERS,
            json={"description": "Descripción actualizada."},
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Descripción actualizada."

        phone = await client.post(
            f"/api/admin/clinics/{clinic_id}/phone-numbers",
            headers=ADMIN_HEADERS,
            json={
                "provider": "voipstudio",
                "phone_number": "+34910000123",
                "label": "Recepción",
                "sip_target": "sip:proj_test@sip.api.openai.com;transport=tls",
                "is_active": True,
            },
        )
        assert phone.status_code == 201

        worker = await client.post(
            f"/api/admin/clinics/{clinic_id}/workers",
            headers=ADMIN_HEADERS,
            json={
                "name": "Ana",
                "role": "Médica",
                "public_description": "Consulta general.",
                "calendar_id": "ana@calendar.test",
                "color_id": "2",
                "phone_extension": "101",
                "email": "ana@clinic.test",
                "working_hours_json": {"monday": [{"start": "09:00", "end": "17:00"}]},
            },
        )
        assert worker.status_code == 201
        worker_id = worker.json()["id"]

        service = await client.post(
            f"/api/admin/clinics/{clinic_id}/services",
            headers=ADMIN_HEADERS,
            json={
                "name": "Consulta general",
                "public_name": "Consulta general",
                "description": "Consulta de prueba.",
                "price_text": "50 €",
                "price_amount": "50.00",
                "currency": "eur",
                "duration_minutes": 30,
                "allowed_worker_ids": [worker_id],
            },
        )
        assert service.status_code == 201, service.text
        assert service.json()["currency"] == "EUR"
        assert service.json()["allowed_worker_ids"] == [worker_id]

        services_for_worker = await client.get(
            (f"/api/admin/clinics/{clinic_id}/services?worker_id={worker_id}"),
            headers=ADMIN_HEADERS,
        )
        assert services_for_worker.status_code == 200
        assert services_for_worker.json()["total"] == 1

        invalid_duration = await client.post(
            f"/api/admin/clinics/{clinic_id}/services",
            headers=ADMIN_HEADERS,
            json={
                "name": "Inválido",
                "public_name": "Inválido",
                "duration_minutes": 0,
            },
        )
        assert invalid_duration.status_code == 422

        deleted_phone = await client.delete(
            (f"/api/admin/clinics/{clinic_id}/phone-numbers/{phone.json()['id']}"),
            headers=ADMIN_HEADERS,
        )
        assert deleted_phone.status_code == 200


@pytest.mark.anyio
async def test_assistant_knowledge_and_flow_crud(database_engine: Engine) -> None:
    """Prompt versions, LLM context, and flows should be independently managed."""
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Contexto")
        clinic_id = clinic["id"]
        config_payload = {
            "name": "Principal",
            "realtime_model": "gpt-realtime-2",
            "realtime_voice": "marin",
            "language": "es",
            "first_message": "Hola. Soy el asistente virtual.",
            "system_prompt": "Gestiona citas.",
            "safety_prompt": "No diagnostiques.",
            "booking_policy_prompt": "Confirma antes de reservar.",
            "cancellation_policy_prompt": "Confirma antes de cancelar.",
            "transfer_policy_prompt": "Transfiere si se solicita.",
            "tone": "cercano",
            "response_length": "corta",
            "ask_patient_name": True,
            "ask_patient_phone": True,
            "ask_general_reason": True,
            "allow_booking_without_worker": True,
            "max_proposed_slots": 2,
            "allow_cancellations": True,
            "allow_reschedules": True,
            "natural_confirmation_required": True,
            "avoid_exact_confirmation_phrases": True,
            "additional_instructions": "Habla natural.",
            "forbidden_phrases": "No diga esto",
            "no_availability_message": "No hay huecos.",
            "missing_calendar_message": "Falta calendario.",
            "emergency_message": "Llame al 112.",
            "human_transfer_message": "Le paso con una persona.",
            "closing_message": "Hasta luego.",
            "use_prices": True,
            "use_knowledge_base": True,
            "strict_calendar_mode": True,
            "transcript_enabled": True,
            "recording_enabled": False,
            "conversation_retention_days": 45,
            "is_active": True,
        }
        first_config = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json=config_payload,
        )
        assert first_config.status_code == 201
        assert first_config.json()["tone"] == "cercano"
        assert first_config.json()["max_proposed_slots"] == 2

        second_active = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={**config_payload, "name": "Segundo"},
        )
        assert second_active.status_code == 409

        inactive_config = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={
                **config_payload,
                "name": "Alternativa",
                "first_message": "Hola desde la alternativa.",
                "system_prompt": "Usa esta configuración seleccionada.",
                "is_active": False,
            },
        )
        assert inactive_config.status_code == 201

        updated_config = await client.patch(
            (
                f"/api/admin/clinics/{clinic_id}/assistant-configs/"
                f"{inactive_config.json()['id']}"
            ),
            headers=ADMIN_HEADERS,
            json={
                "realtime_voice": "cedar",
                "language": "gl-ES",
                "conversation_retention_days": 60,
                "tone": "formal",
                "max_proposed_slots": 4,
            },
        )
        assert updated_config.status_code == 200
        assert updated_config.json()["realtime_voice"] == "cedar"
        assert updated_config.json()["language"] == "gl-ES"
        assert updated_config.json()["conversation_retention_days"] == 60
        assert updated_config.json()["tone"] == "formal"
        assert updated_config.json()["max_proposed_slots"] == 4

        selected_preview = await client.post(
            (
                f"/api/admin/clinics/{clinic_id}/assistant-configs/"
                f"{inactive_config.json()['id']}/preview-prompt"
            ),
            headers=ADMIN_HEADERS,
        )
        assert selected_preview.status_code == 200
        assert "Hola desde la alternativa." in selected_preview.json()["prompt"]
        assert (
            "Usa esta configuración seleccionada."
            in selected_preview.json()["prompt"]
        )

        activated = await client.post(
            (
                f"/api/admin/clinics/{clinic_id}/assistant-configs/"
                f"{inactive_config.json()['id']}/activate"
            ),
            headers=ADMIN_HEADERS,
        )
        assert activated.status_code == 200
        assert activated.json()["is_active"] is True

        listed_configs = await client.get(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
        )
        active_ids = [
            item["id"]
            for item in listed_configs.json()["items"]
            if item["is_active"]
        ]
        assert active_ids == [inactive_config.json()["id"]]

        invalid_config = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={"name": "Incompleta"},
        )
        assert invalid_config.status_code == 422

        assistant_options = await client.get(
            "/api/admin/assistant-options",
            headers=ADMIN_HEADERS,
        )
        assert assistant_options.status_code == 200
        assert assistant_options.json()["default_model"] == "gpt-realtime-2"
        assert {"marin", "cedar"}.issubset(
            {voice["id"] for voice in assistant_options.json()["voices"]}
        )
        assert "openai" in {
            provider["id"]
            for provider in assistant_options.json()["voice_providers"]
        }
        assert "mp3" in assistant_options.json()["output_audio_formats"]
        assert "gl-ES" in {
            language["id"]
            for language in assistant_options.json()["languages"]
        }
        recommended_template = await client.get(
            "/api/admin/assistant-templates/recommended",
            headers=ADMIN_HEADERS,
        )
        assert recommended_template.status_code == 200
        assert recommended_template.json()["avoid_exact_confirmation_phrases"] is True

        knowledge = await client.post(
            f"/api/admin/clinics/{clinic_id}/knowledge",
            headers=ADMIN_HEADERS,
            json={
                "title": "Precio consulta",
                "category": "prices",
                "content": "La consulta cuesta 50 €.",
                "priority": 100,
            },
        )
        assert knowledge.status_code == 201

        service = await client.post(
            f"/api/admin/clinics/{clinic_id}/services",
            headers=ADMIN_HEADERS,
            json={
                "name": "Consulta preview",
                "public_name": "Consulta preview",
                "price_text": "70 €",
                "duration_minutes": 30,
                "is_bookable_by_bot": False,
            },
        )
        assert service.status_code == 201

        inactive_service = await client.post(
            f"/api/admin/clinics/{clinic_id}/services",
            headers=ADMIN_HEADERS,
            json={
                "name": "Servicio oculto",
                "public_name": "Servicio oculto",
                "duration_minutes": 20,
                "is_active": False,
            },
        )
        assert inactive_service.status_code == 201

        inactive_knowledge = await client.post(
            f"/api/admin/clinics/{clinic_id}/knowledge",
            headers=ADMIN_HEADERS,
            json={
                "title": "Contexto oculto",
                "category": "custom",
                "content": "No debe entrar en el prompt.",
                "is_active": False,
            },
        )
        assert inactive_knowledge.status_code == 201

        flow = await client.post(
            f"/api/admin/clinics/{clinic_id}/flows",
            headers=ADMIN_HEADERS,
            json={
                "name": "Reserva estándar",
                "description": "Flujo estándar.",
                "flow_json": {
                    "name": "Reserva estándar",
                    "objectives": ["Crear una cita confirmada."],
                    "exit_conditions": ["La cita queda creada."],
                    "steps": [
                        {
                            "id": "collect_patient_name",
                            "type": "collect",
                            "field": "patient_name",
                            "required": True,
                        },
                        {
                            "id": "propose_slots",
                            "type": "tool",
                            "tool_name": "propose_slots",
                        },
                        {
                            "id": "confirm",
                            "type": "confirmation",
                            "required": True,
                        },
                        {
                            "id": "create",
                            "type": "tool",
                            "tool_name": "create_appointment",
                        },
                    ],
                },
            },
        )
        assert flow.status_code == 201

        invalid_flow = await client.post(
            f"/api/admin/clinics/{clinic_id}/flows",
            headers=ADMIN_HEADERS,
            json={
                "name": "Inválido",
                "flow_json": {"name": "Inválido", "steps": []},
            },
        )
        assert invalid_flow.status_code == 422

        unknown_tool_flow = await client.post(
            f"/api/admin/clinics/{clinic_id}/flows",
            headers=ADMIN_HEADERS,
            json={
                "name": "Tool inválida",
                "flow_json": {
                    "name": "Tool inválida",
                    "steps": [
                        {
                            "id": "bad_tool",
                            "type": "tool",
                            "tool_name": "invented_tool",
                        }
                    ],
                },
            },
        )
        assert unknown_tool_flow.status_code == 422

        unknown_field_flow = await client.post(
            f"/api/admin/clinics/{clinic_id}/flows",
            headers=ADMIN_HEADERS,
            json={
                "name": "Campo inválido",
                "flow_json": {
                    "name": "Campo inválido",
                    "steps": [
                        {
                            "id": "medical_data",
                            "type": "collect",
                            "field": "medical_history",
                            "required": True,
                        }
                    ],
                },
            },
        )
        assert unknown_field_flow.status_code == 422

        templates = await client.get(
            f"/api/admin/clinics/{clinic_id}/flow-templates",
            headers=ADMIN_HEADERS,
        )
        assert templates.status_code == 200
        standard_template = next(
            item
            for item in templates.json()
            if item["key"] == "standard_booking"
        )
        assert any(
            step.get("tool_name") == "create_appointment"
            for step in standard_template["flow_json"]["steps"]
        )

        associated = await client.patch(
            (
                f"/api/admin/clinics/{clinic_id}/assistant-configs/"
                f"{first_config.json()['id']}"
            ),
            headers=ADMIN_HEADERS,
            json={"conversation_flow_id": flow.json()["id"]},
        )
        assert associated.status_code == 200
        assert associated.json()["conversation_flow_id"] == flow.json()["id"]

        flow_preview = await client.post(
            (
                f"/api/admin/clinics/{clinic_id}/flows/{flow.json()['id']}"
                f"/preview-prompt?config_id={first_config.json()['id']}"
            ),
            headers=ADMIN_HEADERS,
        )
        assert flow_preview.status_code == 200
        assert "Flujo conversacional activo: Reserva estándar" in (
            flow_preview.json()["prompt"]
        )
        assert "patient_name" in flow_preview.json()["prompt"]
        assert "propose_slots" in flow_preview.json()["prompt"]

        listed = await client.get(
            f"/api/admin/clinics/{clinic_id}/knowledge?category=prices",
            headers=ADMIN_HEADERS,
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["title"] == "Precio consulta"

        preview = await client.post(
            (
                f"/api/admin/clinics/{clinic_id}/assistant-configs/"
                f"{first_config.json()['id']}/preview-prompt"
            ),
            headers=ADMIN_HEADERS,
        )
        assert preview.status_code == 200
        preview_body = preview.json()
        assert preview_body["realtime_model"] == "gpt-realtime-2"
        assert "Consulta preview" in preview_body["prompt"]
        assert "70 €" in preview_body["prompt"]
        assert "Precio consulta" in preview_body["prompt"]
        assert "Servicio oculto" not in preview_body["prompt"]
        assert "Contexto oculto" not in preview_body["prompt"]
        assert "no reservar con el asistente" in preview_body["prompt"]
        assert "Flujo conversacional activo: Reserva estándar" in (
            preview_body["prompt"]
        )

        context_preview = await client.get(
            f"/api/admin/clinics/{clinic_id}/prompt-context-preview",
            headers=ADMIN_HEADERS,
        )
        assert context_preview.status_code == 200
        context_body = context_preview.json()
        assert [item["public_name"] for item in context_body["services"]] == [
            "Consulta preview"
        ]
        assert context_body["services"][0]["price"] == "70 €"
        assert context_body["services"][0]["is_bookable_by_bot"] is False
        assert [item["title"] for item in context_body["knowledge_items"]] == [
            "Precio consulta"
        ]
        assert "No hay servicios reservables." in context_body["warnings"]

        searched = await client.get(
            f"/api/admin/clinics/{clinic_id}/knowledge?q=consulta",
            headers=ADMIN_HEADERS,
        )
        assert searched.status_code == 200
        assert searched.json()["total"] == 1


@pytest.mark.anyio
async def test_assistant_dual_call_audio_policy(database_engine: Engine) -> None:
    """External voice providers should force VPS media bridge safely."""
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Audio")
        clinic_id = clinic["id"]
        base_payload = {
            "name": "Principal",
            "realtime_model": "gpt-realtime-2",
            "realtime_voice": "marin",
            "language": "es",
            "first_message": "Hola, soy el asistente virtual.",
            "system_prompt": "Gestiona citas.",
            "safety_prompt": "No diagnostiques.",
            "booking_policy_prompt": "Propón huecos reales.",
            "cancellation_policy_prompt": "Confirma antes de cancelar.",
            "transfer_policy_prompt": "Transfiere si se solicita.",
        }

        openai_config = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json=base_payload,
        )
        assert openai_config.status_code == 201, openai_config.text
        assert openai_config.json()["voice_provider"] == "openai"
        assert openai_config.json()["call_audio_mode"] == "openai_hosted_sip"

        azure_config = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={
                **base_payload,
                "name": "Azure",
                "voice_provider": "azure",
                "call_audio_mode": "openai_hosted_sip",
                "voice_id": "es-ES-ElviraNeural",
            },
        )
        assert azure_config.status_code == 201, azure_config.text
        assert azure_config.json()["voice_provider"] == "azure"
        assert azure_config.json()["call_audio_mode"] == "vps_media_bridge"

        cloned_without_confirmation = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={
                **base_payload,
                "name": "ElevenLabs",
                "voice_provider": "elevenlabs",
                "call_audio_mode": "vps_media_bridge",
                "voice_id": "custom_voice",
            },
        )
        assert cloned_without_confirmation.status_code == 422

        cloned_confirmed = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={
                **base_payload,
                "name": "ElevenLabs confirmado",
                "voice_provider": "elevenlabs",
                "call_audio_mode": "openai_hosted_sip",
                "voice_id": "custom_voice",
                "external_voice_legal_confirmed": True,
            },
        )
        assert cloned_confirmed.status_code == 201, cloned_confirmed.text
        assert cloned_confirmed.json()["call_audio_mode"] == "vps_media_bridge"


@pytest.mark.anyio
async def test_voice_provider_catalog_endpoints(database_engine: Engine) -> None:
    """Admin UI should discover providers and synchronized voices from backend."""
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        providers = await client.get(
            "/api/admin/voice-providers",
            headers=ADMIN_HEADERS,
        )
        assert providers.status_code == 200
        provider_ids = {item["id"] for item in providers.json()}
        assert {"openai", "azure", "google", "elevenlabs"}.issubset(provider_ids)

        synced = await client.post(
            "/api/admin/voice-providers/sync",
            headers=ADMIN_HEADERS,
        )
        assert synced.status_code == 200
        assert synced.json()["synced"]["openai"] >= 1
        assert synced.json()["synced"]["azure"] >= 1

        openai_voices = await client.get(
            "/api/admin/voice-providers/openai/voices",
            headers=ADMIN_HEADERS,
        )
        assert openai_voices.status_code == 200
        assert {"marin", "cedar"}.issubset(
            {item["voice_id"] for item in openai_voices.json()}
        )

        missing = await client.get(
            "/api/admin/voice-providers/nope/voices",
            headers=ADMIN_HEADERS,
        )
        assert missing.status_code == 404


@pytest.mark.anyio
async def test_assistant_voice_preview_returns_audio(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The assistant editor should preview voice without creating a conversation."""
    calls: list[tuple[str, str, str, str | None, str | None, str]] = []

    def fake_speech(
        settings: object,
        *,
        provider: str,
        text: str,
        voice: str,
        model: str | None = None,
        instructions: str | None = None,
        response_format: str = "mp3",
        **kwargs: object,
    ) -> TTSResult:
        calls.append((provider, text, voice, model, instructions, response_format))
        return TTSResult(audio=b"audio-bytes", media_type="audio/wav")

    monkeypatch.setattr(core_api, "synthesize_speech", fake_speech)
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Voz")
        response = await client.post(
            f"/api/admin/clinics/{clinic['id']}/assistant-configs/voice-preview",
            headers=ADMIN_HEADERS,
            json={
                "text": "Hola, soy el asistente.",
                "realtime_voice": "marin",
                "realtime_model": "gpt-realtime-2",
                "tts_preview_voice": "cedar",
                "voice_instructions": "Habla claro.",
                "preview_audio_format": "wav",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"audio-bytes"
    assert len(calls) == 1
    (
        call_provider,
        call_text,
        call_voice,
        call_model,
        call_instructions,
        call_format,
    ) = calls[0]
    assert call_provider == "openai"
    assert call_text == "Hola, soy el asistente."
    assert call_voice == "cedar"
    assert call_model == "gpt-realtime-2"
    assert call_format == "wav"
    assert call_instructions is not None
    assert "Perfil de voz" in call_instructions
    assert "Habla claro." in call_instructions


@pytest.mark.anyio
async def test_realtime_preview_session_lifecycle(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assistant config editor should create, heartbeat, tool, and close previews."""

    class FakeOpenAIResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"client_secret": {"value": "ephemeral-test-secret"}}

    monkeypatch.setattr(
        realtime_preview_service.httpx,
        "post",
        lambda *args, **kwargs: FakeOpenAIResponse(),
    )
    monkeypatch.setattr(
        realtime_preview_api,
        "execute_preview_tool",
        lambda *args, **kwargs: {"ok": True, "clinic_name": "Demo"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Realtime")
        clinic_id = clinic["id"]
        config_payload = {
            "name": "Principal",
            "realtime_model": "gpt-realtime-2",
            "realtime_voice": "marin",
            "language": "es",
            "first_message": "Hola, soy el asistente virtual.",
            "system_prompt": "Gestiona citas.",
            "safety_prompt": "No diagnostiques.",
            "booking_policy_prompt": "Propón huecos reales.",
            "cancellation_policy_prompt": "Confirma antes de cancelar.",
            "transfer_policy_prompt": "Transfiere si se solicita.",
        }
        created_config = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs",
            headers=ADMIN_HEADERS,
            json={**config_payload, "is_active": True},
        )
        assert created_config.status_code == 201, created_config.text

        started = await client.post(
            f"/api/admin/clinics/{clinic_id}/assistant-configs/realtime-preview-sessions",
            headers=ADMIN_HEADERS,
            json={
                "assistant_config_id": created_config.json()["id"],
                "config": {**config_payload, "is_active": False},
            },
        )
        assert started.status_code == 201, started.text
        body = started.json()
        assert body["client_secret"] == "ephemeral-test-secret"
        session_id = body["id"]

        heartbeat = await client.post(
            f"/api/admin/realtime-preview-sessions/{session_id}/heartbeat",
            headers=ADMIN_HEADERS,
        )
        assert heartbeat.status_code == 200

        tool = await client.post(
            f"/api/admin/realtime-preview-sessions/{session_id}/tool-call",
            headers=ADMIN_HEADERS,
            json={"name": "get_clinic_info", "call_id": "call_1", "arguments": {}},
        )
        assert tool.status_code == 200
        assert tool.json()["output"]["ok"] is True

        closed = await client.delete(
            f"/api/admin/realtime-preview-sessions/{session_id}",
            headers=ADMIN_HEADERS,
        )
        assert closed.status_code == 204


@pytest.mark.anyio
async def test_knowledge_pdf_and_url_imports(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Knowledge imports should preview extracted text and persist metadata."""
    monkeypatch.setattr(
        content_api,
        "extract_pdf_knowledge",
        lambda data, filename: ExtractedKnowledge(
            title="Tarifas demo",
            content=f"PDF extraído desde {filename}: limpieza 50 euros.",
            source=filename,
        ),
    )
    monkeypatch.setattr(
        content_api,
        "fetch_url_knowledge",
        lambda url: ExtractedKnowledge(
            title="FAQ web",
            content="Horario de atención de lunes a viernes.",
            source=url,
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Imports")
        clinic_id = clinic["id"]
        pdf_preview = await client.post(
            f"/api/admin/clinics/{clinic_id}/knowledge/import/pdf/preview",
            headers=ADMIN_HEADERS,
            files={"file": ("tarifas.pdf", b"%PDF-demo", "application/pdf")},
            data={"category": "prices"},
        )
        assert pdf_preview.status_code == 200
        assert pdf_preview.json()["source_type"] == "pdf"
        assert "limpieza 50" in pdf_preview.json()["content"]

        pdf_import = await client.post(
            f"/api/admin/clinics/{clinic_id}/knowledge/import/pdf",
            headers=ADMIN_HEADERS,
            files={"file": ("tarifas.pdf", b"%PDF-demo", "application/pdf")},
            data={
                "category": "prices",
                "title": "Tarifas 2026",
                "priority": "80",
                "is_active": "true",
            },
        )
        assert pdf_import.status_code == 201
        assert pdf_import.json()["title"] == "Tarifas 2026"
        assert pdf_import.json()["source_type"] == "pdf"
        assert pdf_import.json()["import_status"] == "imported"

        url_preview = await client.post(
            f"/api/admin/clinics/{clinic_id}/knowledge/import/url/preview",
            headers=ADMIN_HEADERS,
            json={"url": "https://example.test/faq", "category": "faq"},
        )
        assert url_preview.status_code == 200
        assert url_preview.json()["source_type"] == "url"
        assert "Horario de atención" in url_preview.json()["content"]

        url_import = await client.post(
            f"/api/admin/clinics/{clinic_id}/knowledge/import/url",
            headers=ADMIN_HEADERS,
            json={
                "url": "https://example.test/faq",
                "category": "faq",
                "priority": 20,
                "is_active": True,
            },
        )
        assert url_import.status_code == 201
        assert url_import.json()["source_type"] == "url"

    with _factory(database_engine)() as session:
        imported = session.scalars(
            select(KnowledgeItem).where(KnowledgeItem.clinic_id == clinic_id)
        ).all()
        assert {item.source_type for item in imported} == {"pdf", "url"}


@pytest.mark.anyio
async def test_call_conversation_filters_and_update(
    database_engine: Engine,
) -> None:
    """Calls should expose outcomes, transcripts, and raw event conversations."""
    factory = _factory(database_engine)
    with factory() as session:
        clinic = Clinic(
            name="Clínica Llamadas",
            timezone="Europe/Madrid",
            phone_number="+34910000444",
        )
        worker = Worker(
            clinic=clinic,
            name="Ana",
            role="Médica",
            working_hours_json={},
        )
        service = Service(
            clinic=clinic,
            name="Consulta",
            public_name="Consulta general",
            duration_minutes=30,
        )
        started_at = datetime.now(UTC) - timedelta(minutes=6)
        call = CallSession(
            clinic=clinic,
            openai_call_id="call-admin-test",
            caller_phone="+34600000444",
            called_number=clinic.phone_number,
            status=CallStatus.COMPLETED,
            outcome=CallOutcome.APPOINTMENT_CREATED,
            transcript_enabled=True,
            transcript_text="Paciente: Hola.",
            summary_text="Cita creada con Ana.",
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=5),
        )
        appointment_start = datetime.now(UTC) + timedelta(days=1)
        appointment = Appointment(
            clinic=clinic,
            worker=worker,
            service=service,
            call_session=call,
            google_calendar_id="ana@example.test",
            google_event_id="event-call-analysis",
            patient_name="Marta",
            patient_phone="+34600000444",
            reason="Consulta",
            start_at=appointment_start,
            end_at=appointment_start + timedelta(minutes=30),
            status=AppointmentStatus.CONFIRMED,
            source=AppointmentSource.VOICE_BOT,
        )
        events = [
            CallEvent(
                call_session=call,
                event_type="conversation.test",
                payload_json={"text": "Hola"},
            ),
            CallEvent(
                call_session=call,
                event_type="response.function_call_arguments.done",
                payload_json={
                    "type": "response.function_call_arguments.done",
                    "name": "create_appointment",
                },
            ),
            CallEvent(
                call_session=call,
                event_type="response.failed",
                payload_json={"error": "simulated diagnostic error"},
            ),
        ]
        session.add_all([clinic, worker, service, call, appointment, *events])
        session.commit()
        clinic_id = clinic.id
        call_id = call.id
        appointment_id = appointment.id
        worker_id = worker.id
        service_id = service.id

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        imported = await client.post(
            f"/api/admin/clinics/{clinic_id}/calls",
            headers=ADMIN_HEADERS,
            json={
                "openai_call_id": "call-imported-test",
                "caller_phone": "+34600000555",
                "called_number": "+34910000444",
                "status": "failed",
                "outcome": "failed",
            },
        )
        assert imported.status_code == 201

        listed = await client.get(
            (
                f"/api/admin/clinics/{clinic_id}/calls"
                f"?active=false&outcome=appointment_created"
                f"&phone=600000444&worker_id={worker_id}&service_id={service_id}"
            ),
            headers=ADMIN_HEADERS,
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["duration_seconds"] == 300
        assert listed.json()["items"][0]["appointment"]["worker_name"] == "Ana"

        detail = await client.get(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}",
            headers=ADMIN_HEADERS,
        )
        assert detail.status_code == 200
        assert detail.json()["events"][0]["event_type"] == "conversation.test"
        assert len(detail.json()["tool_calls"]) == 1
        assert len(detail.json()["errors"]) == 1
        assert detail.json()["appointment"]["service_name"] == "Consulta general"

        tool_calls = await client.get(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}/tool-calls",
            headers=ADMIN_HEADERS,
        )
        assert tool_calls.status_code == 200
        assert tool_calls.json()[0]["payload_json"]["name"] == "create_appointment"

        updated = await client.patch(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}",
            headers=ADMIN_HEADERS,
            json={
                "caller_name": "Marta",
                "detected_intent": "ask_information",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["caller_name"] == "Marta"

        cleared = await client.delete(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}/content",
            headers=ADMIN_HEADERS,
        )
        assert cleared.status_code == 200
        assert cleared.json()["appointment_preserved"] is True

        debug = await client.get(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}/debug",
            headers=ADMIN_HEADERS,
        )
        assert debug.status_code == 200
        assert debug.json()["call"]["transcript_text"] is None

        anonymized = await client.post(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}/anonymize-phone",
            headers=ADMIN_HEADERS,
        )
        assert anonymized.status_code == 200
        assert anonymized.json()["status"] == "phone_anonymized"

        removed = await client.delete(
            f"/api/admin/clinics/{clinic_id}/calls/{call_id}",
            headers=ADMIN_HEADERS,
        )
        assert removed.status_code == 200
        assert removed.json()["status"] == "anonymized"

        imported_id = imported.json()["id"]
        removed_import = await client.delete(
            f"/api/admin/clinics/{clinic_id}/calls/{imported_id}",
            headers=ADMIN_HEADERS,
        )
        assert removed_import.status_code == 200
        assert removed_import.json()["status"] == "deleted"

    with factory() as session:
        stored_appointment = session.get(Appointment, appointment_id)
        assert stored_appointment is not None
        assert stored_appointment.call_session_id == call_id


@pytest.mark.anyio
async def test_admin_appointment_crud_and_filters(database_engine: Engine) -> None:
    """The panel should manage local appointments with tenant-safe relations."""
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "Citas")
        clinic_id = clinic["id"]
        worker = await client.post(
            f"/api/admin/clinics/{clinic_id}/workers",
            headers=ADMIN_HEADERS,
            json={
                "name": "Luis",
                "role": "Médico",
                "working_hours_json": {},
            },
        )
        service = await client.post(
            f"/api/admin/clinics/{clinic_id}/services",
            headers=ADMIN_HEADERS,
            json={
                "name": "Revisión",
                "public_name": "Revisión",
                "duration_minutes": 45,
            },
        )
        start_at = datetime.now(UTC) + timedelta(days=2)
        end_at = start_at + timedelta(minutes=45)
        appointment = await client.post(
            f"/api/admin/clinics/{clinic_id}/appointments",
            headers=ADMIN_HEADERS,
            json={
                "worker_id": worker.json()["id"],
                "service_id": service.json()["id"],
                "patient_name": "Marta",
                "patient_phone": "+34600000111",
                "reason": "Revisión general",
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            },
        )
        assert appointment.status_code == 201, appointment.text
        assert appointment.json()["source"] == "admin_panel"
        appointment_id = appointment.json()["id"]

        overlapping = await client.post(
            f"/api/admin/clinics/{clinic_id}/appointments",
            headers=ADMIN_HEADERS,
            json={
                "worker_id": worker.json()["id"],
                "patient_name": "Otra persona",
                "patient_phone": "+34600000222",
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            },
        )
        assert overlapping.status_code == 409

        filtered = await client.get(
            (
                f"/api/admin/clinics/{clinic_id}/appointments"
                f"?worker_id={worker.json()['id']}&service_id={service.json()['id']}"
            ),
            headers=ADMIN_HEADERS,
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["worker_name"] == "Luis"
        assert filtered.json()["items"][0]["service_name"] == "Revisión"

        cancelled = await client.post(
            (
                f"/api/admin/clinics/{clinic_id}/appointments/"
                f"{appointment_id}/cancel"
            ),
            headers=ADMIN_HEADERS,
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        deleted = await client.delete(
            f"/api/admin/clinics/{clinic_id}/appointments/{appointment_id}",
            headers=ADMIN_HEADERS,
        )
        assert deleted.status_code == 200


@pytest.mark.anyio
async def test_admin_worker_freebusy_diagnostic(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The panel can test a linked worker calendar without creating events."""
    google_client = MagicMock()
    google_client.freebusy.return_value.query.return_value.execute.return_value = {
        "calendars": {
            "ana@example.test": {
                "busy": [
                    {
                        "start": "2030-01-02T09:00:00+01:00",
                        "end": "2030-01-02T10:00:00+01:00",
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(
        "app.api.admin.core.get_authorized_calendar_client",
        lambda *_args, **_kwargs: google_client,
    )

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        clinic = await _create_clinic(client, "FreeBusy")
        clinic_id = clinic["id"]
        worker = await client.post(
            f"/api/admin/clinics/{clinic_id}/workers",
            headers=ADMIN_HEADERS,
            json={
                "name": "Ana",
                "role": "Médica",
                "calendar_id": "ana@example.test",
                "working_hours_json": {},
            },
        )
        response = await client.post(
            (
                f"/api/admin/clinics/{clinic_id}/workers/"
                f"{worker.json()['id']}/test-freebusy"
            ),
            headers=ADMIN_HEADERS,
            json={
                "time_min": "2030-01-02T08:00:00+01:00",
                "time_max": "2030-01-02T18:00:00+01:00",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["calendar_id"] == "ana@example.test"
    assert len(response.json()["busy_ranges"]) == 1
