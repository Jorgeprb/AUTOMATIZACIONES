"""Tenant resolution and dynamic Realtime prompt tests."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    AssistantConfig,
    Clinic,
    GoogleCredential,
    KnowledgeCategory,
    KnowledgeItem,
    PhoneNumber,
    PhoneProvider,
    Service,
    Worker,
)
from app.openai_realtime.prompt_builder import (
    build_realtime_instructions,
    resolve_clinic_by_called_number,
)


def _assistant_config(clinic: Clinic, *, name: str) -> AssistantConfig:
    """Create a complete active assistant configuration."""
    return AssistantConfig(
        clinic=clinic,
        name=name,
        realtime_model="gpt-realtime-clinic",
        realtime_voice="marin",
        language="es",
        first_message=f"Hola desde {clinic.name}.",
        system_prompt="Gestiona citas y responde con brevedad.",
        safety_prompt="No des consejo médico.",
        booking_policy_prompt="Confirma siempre antes de reservar.",
        cancellation_policy_prompt="Confirma la cita antes de cancelar.",
        transfer_policy_prompt="Transfiere cuando la persona lo pida.",
        is_active=True,
    )


def test_resolve_clinic_by_active_called_number(db_session: Session) -> None:
    """The resolver must select the active number, config, and tenant resources."""
    clinic = Clinic(
        name="Clínica Norte",
        timezone="Europe/Madrid",
        phone_number="+34910001001",
    )
    phone = PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number="+34910001001",
        label="Principal",
    )
    config = _assistant_config(clinic, name="Configuración Norte")
    active_worker = Worker(
        clinic=clinic,
        name="Ana",
        role="Médica",
        calendar_id="ana@calendar.test",
        working_hours_json={"monday": [{"start": "09:00", "end": "14:00"}]},
    )
    inactive_worker = Worker(
        clinic=clinic,
        name="Oculto",
        role="Médico",
        is_active=False,
        working_hours_json={},
    )
    active_service = Service(
        clinic=clinic,
        name="Consulta",
        public_name="Consulta general",
        duration_minutes=30,
    )
    inactive_service = Service(
        clinic=clinic,
        name="Servicio oculto",
        public_name="Servicio oculto",
        duration_minutes=15,
        is_active=False,
    )
    knowledge = KnowledgeItem(
        clinic=clinic,
        title="Acceso",
        category=KnowledgeCategory.LOCATION,
        content="Entrada por Calle Norte.",
    )
    db_session.add_all(
        [
            clinic,
            phone,
            config,
            active_worker,
            inactive_worker,
            active_service,
            inactive_service,
            knowledge,
        ]
    )
    db_session.commit()

    context = resolve_clinic_by_called_number(
        "sip:+34910001001@example.test",
        session=db_session,
    )

    assert context.clinic.id == clinic.id
    assert context.phone_number is not None
    assert context.phone_number.id == phone.id
    assert context.active_assistant_config.id == config.id
    assert [worker.name for worker in context.workers] == ["Ana"]
    assert [service.public_name for service in context.services] == ["Consulta general"]
    assert [item.title for item in context.knowledge_items] == ["Acceso"]


def test_dynamic_prompt_has_prices_knowledge_and_tenant_isolation(
    db_session: Session,
) -> None:
    """Prompt data must be complete for one clinic and exclude every other tenant."""
    clinic = Clinic(
        name="Clínica Centro",
        timezone="Europe/Madrid",
        phone_number="+34910001002",
        address="Calle Centro 2",
        email="publico@centro.test",
        opening_hours_json={"monday": [{"start": "09:00", "end": "18:00"}]},
        emergency_message="Llama al 112.",
    )
    phone = PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number="+34910001002",
        label="Principal",
        sip_target="sip:secret-internal@example.test",
        webhook_url="https://secret-internal.example.test/webhook",
        notes="SECRETO_INTERNO_NO_PROMPT",
    )
    config = _assistant_config(clinic, name="Configuración Centro")
    worker = Worker(
        clinic=clinic,
        name="Luis",
        role="Médico",
        public_description="Atención general.",
        calendar_id="luis@calendar.test",
        working_hours_json={"monday": [{"start": "10:00", "end": "16:00"}]},
    )
    service = Service(
        clinic=clinic,
        name="Revisión",
        public_name="Revisión",
        description="Seguimiento general.",
        price_amount=Decimal("65.00"),
        currency="EUR",
        duration_minutes=45,
    )
    knowledge = KnowledgeItem(
        clinic=clinic,
        title="Seguro",
        category=KnowledgeCategory.INSURANCE,
        content="Consulta en recepción la cobertura de tu póliza.",
    )
    credential = GoogleCredential(
        clinic=clinic,
        account_email="calendar@centro.test",
        token_json_encrypted="TOKEN_CIFRADO_NO_PROMPT",
    )

    other_clinic = Clinic(
        name="Clínica Ajena Secreta",
        timezone="Europe/Madrid",
        phone_number="+34910001999",
    )
    other_phone = PhoneNumber(
        clinic=other_clinic,
        provider=PhoneProvider.OTHER,
        phone_number="+34910001999",
        label="Ajeno",
    )
    other_config = _assistant_config(other_clinic, name="Config Ajena")
    other_service = Service(
        clinic=other_clinic,
        name="Servicio Ajeno",
        public_name="Servicio Ajeno Confidencial",
        duration_minutes=20,
    )
    other_knowledge = KnowledgeItem(
        clinic=other_clinic,
        title="Dato ajeno",
        category=KnowledgeCategory.CUSTOM,
        content="CONTENIDO_AJENO_NO_DEBE_APARECER",
    )
    db_session.add_all(
        [
            clinic,
            phone,
            config,
            worker,
            service,
            knowledge,
            credential,
            other_clinic,
            other_phone,
            other_config,
            other_service,
            other_knowledge,
        ]
    )
    db_session.commit()

    context = resolve_clinic_by_called_number(
        "+34910001002",
        session=db_session,
    )
    prompt = build_realtime_instructions(context)

    assert "Clínica Centro" in prompt
    assert "Revisión" in prompt
    assert "65.00 EUR" in prompt
    assert "Seguro" in prompt
    assert "Consulta en recepción la cobertura" in prompt
    assert "Luis" in prompt
    assert f"service_id real={service.id}" in prompt
    assert f"worker_id real={worker.id}" in prompt
    assert "envía service_id y no envíes" in prompt
    assert "duration_minutes solo cuando no tengas service_id" in prompt
    assert "Nunca inventes worker_id ni service_id" in prompt
    assert "No pidas frases exactas" in prompt
    assert "aceptación natural" in prompt
    assert "Nunca inventes precios, servicios, trabajadores" in prompt
    assert "Llame al 112 ahora o acuda a urgencias" in prompt
    assert "f1b2d3c4-5678-4abc-9def-1234567890ab" not in prompt
    assert "c0ffeec0-0000-4000-8000-000000000001" not in prompt
    assert "Clínica Ajena Secreta" not in prompt
    assert "Servicio Ajeno Confidencial" not in prompt
    assert "CONTENIDO_AJENO_NO_DEBE_APARECER" not in prompt
    assert "secret-internal" not in prompt
    assert "SECRETO_INTERNO_NO_PROMPT" not in prompt
    assert "TOKEN_CIFRADO_NO_PROMPT" not in prompt


def test_dynamic_prompt_respects_assistant_behavior_fields(
    db_session: Session,
) -> None:
    """Configured behavior fields must change the rendered prompt."""
    clinic = Clinic(
        name="Clínica Configurable",
        timezone="Europe/Madrid",
        phone_number="+34910001003",
    )
    PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number="+34910001003",
        label="Principal",
    )
    config = _assistant_config(clinic, name="Config avanzada")
    config.tone = "comercial"
    config.response_length = "corta"
    config.conversation_style = "natural"
    config.initiative_level = "alto"
    config.max_consecutive_questions = 1
    config.allow_bookings = True
    config.allow_price_answers = False
    config.ask_service = True
    config.commercial_call_handling = "declinar"
    config.commercial_call_message = "No atendemos llamadas comerciales."
    config.human_transfer_rules = "Transfiere quejas y dudas fuera de alcance."
    config.conversation_extra_rules = "No repitas preguntas."
    config.max_proposed_slots = 1
    config.allow_cancellations = False
    config.use_prices = False
    config.use_knowledge_base = False
    config.strict_calendar_mode = True
    config.no_availability_message = "No hay huecos en esa franja."
    config.missing_calendar_message = "Falta calendario del profesional."
    config.emergency_message = "Mensaje urgente personalizado."
    config.human_transfer_message = "Le paso con recepción."
    config.closing_message = "Gracias y hasta luego."
    config.additional_instructions = "Sé comercial, pero breve."
    config.forbidden_phrases = "garantizado al 100%"
    Service(
        clinic=clinic,
        name="Servicio",
        public_name="Servicio con precio",
        price_amount=Decimal("25.00"),
        duration_minutes=30,
    )
    KnowledgeItem(
        clinic=clinic,
        title="Dato ocultable",
        category=KnowledgeCategory.CUSTOM,
        content="Esto no debe entrar si knowledge está apagado.",
    )
    db_session.add(clinic)
    db_session.commit()

    context = resolve_clinic_by_called_number("+34910001003", session=db_session)
    prompt = build_realtime_instructions(context)

    assert "Tono configurado: comercial" in prompt
    assert "Longitud de respuesta: corta" in prompt
    assert "Propón como máximo 1 horarios" in prompt
    assert "Cancelaciones permitidas: no" in prompt
    assert "Uso de precios desactivado" in prompt
    assert "Estilo conversacional: natural" in prompt
    assert "Nivel de iniciativa: alto" in prompt
    assert "No atendemos llamadas comerciales" in prompt
    assert "Transfiere quejas" in prompt
    assert "pending_slots" in prompt
    assert "No repitas preguntas" in prompt
    assert "25.00 EUR" not in prompt
    assert "Base de conocimiento desactivada" in prompt
    assert "Esto no debe entrar" not in prompt
    assert "No hay huecos en esa franja" in prompt
    assert "Falta calendario del profesional" in prompt
    assert "Mensaje urgente personalizado" in prompt
    assert "Le paso con recepción" in prompt
    assert "Gracias y hasta luego" in prompt
    assert "Sé comercial" in prompt
    assert "garantizado al 100%" in prompt
