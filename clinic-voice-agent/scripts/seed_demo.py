"""Create an idempotent demo clinic with workers and services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session_factory
from app.models import (
    AssistantConfig,
    Clinic,
    ConversationFlow,
    KnowledgeCategory,
    KnowledgeItem,
    PhoneNumber,
    PhoneProvider,
    Service,
    Worker,
)
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)

DEMO_WORKING_HOURS = {
    "monday": [{"start": "09:00", "end": "17:00"}],
    "tuesday": [{"start": "09:00", "end": "17:00"}],
    "wednesday": [{"start": "09:00", "end": "17:00"}],
    "thursday": [{"start": "09:00", "end": "17:00"}],
    "friday": [{"start": "09:00", "end": "15:00"}],
}


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    """Objects ensured by the demo seed."""

    clinic: Clinic
    workers: tuple[Worker, Worker]
    services: tuple[Service, ...]
    phone_number: PhoneNumber
    assistant_config: AssistantConfig
    knowledge_items: tuple[KnowledgeItem, ...]
    conversation_flow: ConversationFlow

    @property
    def service(self) -> Service:
        """Keep compatibility with callers expecting the original service."""
        return self.services[0]


def seed_demo(
    session: Session,
    *,
    clinic_name: str,
    clinic_timezone: str,
    clinic_phone_number: str,
) -> DemoSeedResult:
    """Ensure the demo clinic, workers, and default services exist."""
    clinic = session.scalar(
        select(Clinic).where(Clinic.phone_number == clinic_phone_number)
    )
    if clinic is None:
        clinic = Clinic(
            name=clinic_name,
            legal_name="Clínica Demo, S.L.",
            timezone=clinic_timezone,
            phone_number=clinic_phone_number,
            default_language="es",
            address="Calle Demo 10, 28000 Madrid",
            website="https://clinica-demo.example",
            email="recepcion@clinica-demo.example",
            description="Clínica de demostración para probar el panel.",
            opening_hours_json=DEMO_WORKING_HOURS,
            emergency_message=(
                "Si existe una urgencia médica, llama al 112 o acude a urgencias."
            ),
        )
        session.add(clinic)
        session.flush()
    else:
        clinic.legal_name = clinic.legal_name or "Clínica Demo, S.L."
        clinic.address = clinic.address or "Calle Demo 10, 28000 Madrid"
        clinic.website = clinic.website or "https://clinica-demo.example"
        clinic.email = clinic.email or "recepcion@clinica-demo.example"
        clinic.description = (
            clinic.description or "Clínica de demostración para probar el panel."
        )
        clinic.opening_hours_json = clinic.opening_hours_json or DEMO_WORKING_HOURS
        clinic.emergency_message = clinic.emergency_message or (
            "Si existe una urgencia médica, llama al 112 o acude a urgencias."
        )

    worker_specs = (
        {
            "name": "Ana",
            "role": "Médica",
            "calendar_id": None,
            "color_id": "2",
            "public_description": "Medicina general y revisiones.",
            "phone_extension": "101",
            "email": "ana@clinica-demo.example",
        },
        {
            "name": "Luis",
            "role": "Médico",
            "calendar_id": None,
            "color_id": "7",
            "public_description": "Consulta general y seguimiento.",
            "phone_extension": "102",
            "email": "luis@clinica-demo.example",
        },
    )
    workers: list[Worker] = []
    for spec in worker_specs:
        worker = session.scalar(
            select(Worker).where(
                Worker.clinic_id == clinic.id,
                Worker.name == spec["name"],
            )
        )
        if worker is None:
            worker = Worker(
                clinic_id=clinic.id,
                name=spec["name"],
                role=spec["role"],
                calendar_id=spec["calendar_id"],
                color_id=spec["color_id"],
                public_description=spec["public_description"],
                phone_extension=spec["phone_extension"],
                email=spec["email"],
                working_hours_json=DEMO_WORKING_HOURS,
            )
            session.add(worker)
        else:
            worker.public_description = worker.public_description or str(
                spec["public_description"]
            )
            worker.phone_extension = worker.phone_extension or str(
                spec["phone_extension"]
            )
            worker.email = worker.email or str(spec["email"])
        workers.append(worker)

    service_specs = (
        ("Consulta general", 30, "50 €", Decimal("50.00")),
        ("Revisión", 45, "65 €", Decimal("65.00")),
        ("Urgencia no médica", 20, "40 €", Decimal("40.00")),
    )
    services: list[Service] = []
    for service_name, duration_minutes, price_text, price_amount in service_specs:
        service = session.scalar(
            select(Service).where(
                Service.clinic_id == clinic.id,
                Service.name == service_name,
            )
        )
        if service is None:
            service = Service(
                clinic_id=clinic.id,
                name=service_name,
                public_name=service_name,
                description=f"Servicio demo: {service_name}.",
                price_text=price_text,
                price_amount=price_amount,
                duration_minutes=duration_minutes,
                buffer_before_minutes=0,
                buffer_after_minutes=0,
            )
            session.add(service)
        else:
            service.public_name = service_name
            service.description = service.description or (
                f"Servicio demo: {service_name}."
            )
            service.price_text = service.price_text or price_text
            service.price_amount = service.price_amount or price_amount
        services.append(service)

    phone_number = session.scalar(
        select(PhoneNumber).where(PhoneNumber.phone_number == clinic_phone_number)
    )
    if phone_number is None:
        phone_number = PhoneNumber(
            clinic_id=clinic.id,
            provider=PhoneProvider.VOIPSTUDIO,
            phone_number=clinic_phone_number,
            label="Número principal demo",
            sip_target="sip:proj_demo@sip.api.openai.com;transport=tls",
            webhook_url="https://voice.example.test/webhooks/openai/realtime",
            notes="Datos ficticios. Sustituir antes de producción.",
        )
        session.add(phone_number)

    assistant_config = session.scalar(
        select(AssistantConfig).where(
            AssistantConfig.clinic_id == clinic.id,
            AssistantConfig.name == "Asistente principal",
        )
    )
    if assistant_config is None:
        assistant_config = AssistantConfig(
            clinic_id=clinic.id,
            name="Asistente principal",
            realtime_model="gpt-realtime-2",
            realtime_voice="marin",
            language="es",
            first_message=(
                "Hola. Soy el asistente virtual de Clínica Demo. "
                "¿En qué puedo ayudarte?"
            ),
            system_prompt=(
                "Gestiona citas e información general con respuestas breves."
            ),
            safety_prompt=(
                "No diagnostiques ni recomiendes medicación. "
                "Ante una urgencia, indica llamar al 112."
            ),
            booking_policy_prompt=(
                "Propón hasta tres huecos y confirma antes de reservar."
            ),
            cancellation_policy_prompt=(
                "Confirma la cita correcta antes de cancelarla."
            ),
            transfer_policy_prompt=(
                "Transfiere cuando la persona lo solicite o el caso quede fuera "
                "del alcance."
            ),
            is_active=True,
        )
        session.add(assistant_config)

    knowledge_specs = (
        (
            "Ubicación",
            KnowledgeCategory.LOCATION,
            "Estamos en Calle Demo 10, Madrid.",
            100,
        ),
        (
            "Precios orientativos",
            KnowledgeCategory.PRICES,
            "Consulta general 50 €, revisión 65 € y urgencia no médica 40 €.",
            90,
        ),
        (
            "Política de cancelación",
            KnowledgeCategory.POLICY,
            "Las cancelaciones deben solicitarse con la mayor antelación posible.",
            80,
        ),
        (
            "Seguro médico",
            KnowledgeCategory.INSURANCE,
            "La cobertura depende de la póliza. Recepción puede confirmarla.",
            70,
        ),
    )
    knowledge_items: list[KnowledgeItem] = []
    for title, category, content, priority in knowledge_specs:
        item = session.scalar(
            select(KnowledgeItem).where(
                KnowledgeItem.clinic_id == clinic.id,
                KnowledgeItem.title == title,
            )
        )
        if item is None:
            item = KnowledgeItem(
                clinic_id=clinic.id,
                title=title,
                category=category,
                content=content,
                priority=priority,
            )
            session.add(item)
        knowledge_items.append(item)

    conversation_flow = session.scalar(
        select(ConversationFlow).where(
            ConversationFlow.clinic_id == clinic.id,
            ConversationFlow.name == "Reserva estándar",
        )
    )
    if conversation_flow is None:
        conversation_flow = ConversationFlow(
            clinic_id=clinic.id,
            name="Reserva estándar",
            description="Flujo demo de reserva telefónica.",
            flow_json={
                "steps": [
                    "collect_patient",
                    "collect_service",
                    "propose_slots",
                    "confirm",
                    "create_appointment",
                ]
            },
        )
        session.add(conversation_flow)

    session.commit()
    return DemoSeedResult(
        clinic=clinic,
        workers=(workers[0], workers[1]),
        services=tuple(services),
        phone_number=phone_number,
        assistant_config=assistant_config,
        knowledge_items=tuple(knowledge_items),
        conversation_flow=conversation_flow,
    )


def main() -> None:
    """Run the demo seed against the configured database."""
    settings = get_settings()
    configure_logging(settings.log_level)

    with get_session_factory()() as session:
        result = seed_demo(
            session,
            clinic_name=settings.clinic_name,
            clinic_timezone=settings.clinic_timezone,
            clinic_phone_number=settings.clinic_phone_number,
        )

    logger.info(
        "demo_seed_completed",
        extra={
            "clinic_id": str(result.clinic.id),
            "worker_names": [worker.name for worker in result.workers],
            "service_names": [service.name for service in result.services],
            "assistant_config": result.assistant_config.name,
            "knowledge_items": len(result.knowledge_items),
        },
    )


if __name__ == "__main__":
    main()
