"""Resolve tenant-safe clinic context and build Realtime instructions."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversation_flows import render_flow_prompt
from app.db import get_session_factory
from app.models import (
    AssistantConfig,
    Clinic,
    ConversationFlow,
    GoogleCredential,
    KnowledgeItem,
    PhoneNumber,
    Service,
    Worker,
)


class ClinicContextError(LookupError):
    """Base error raised while resolving a call's clinic context."""


class UnknownCalledNumber(ClinicContextError):
    """Raised when no active phone number owns an incoming call."""


class ActiveAssistantConfigMissing(ClinicContextError):
    """Raised when the resolved clinic has no active assistant configuration."""


@dataclass(frozen=True, slots=True)
class CalendarSettings:
    """Safe calendar information relevant to the assistant."""

    timezone: str
    google_calendar_connected: bool
    workers_with_calendar: tuple[str, ...]
    workers_without_calendar: tuple[str, ...]
    opening_hours: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BookingRules:
    """Effective booking behavior derived from clinic configuration."""

    max_proposed_slots: int
    verbal_confirmation_required: bool
    availability_recheck_required: bool
    bookable_services: tuple[str, ...]
    booking_policy: str
    cancellation_policy: str
    transfer_policy: str


@dataclass(frozen=True, slots=True)
class ClinicContext:
    """All tenant-scoped public data needed to configure one voice call."""

    clinic: Clinic
    phone_number: PhoneNumber | None
    active_assistant_config: AssistantConfig
    workers: tuple[Worker, ...]
    services: tuple[Service, ...]
    knowledge_items: tuple[KnowledgeItem, ...]
    active_conversation_flow: ConversationFlow | None
    calendar_settings: CalendarSettings
    booking_rules: BookingRules


def _called_number_candidates(called_number: str) -> tuple[str, ...]:
    """Build normalized exact-match candidates without broad database scans."""
    raw = called_number.strip()
    digits = "".join(character for character in raw if character.isdigit())
    values = {raw}
    if digits:
        values.add(digits)
        values.add(f"+{digits}")
    return tuple(value for value in values if value)


def _load_clinic_context(
    session: Session,
    *,
    clinic: Clinic,
    phone_number: PhoneNumber | None,
    assistant_config: AssistantConfig,
) -> ClinicContext:
    """Load only active, tenant-owned data required by the prompt."""
    workers = tuple(
        session.scalars(
            select(Worker)
            .where(
                Worker.clinic_id == clinic.id,
                Worker.is_active.is_(True),
            )
            .order_by(Worker.name, Worker.id)
        )
    )
    services = tuple(
        session.scalars(
            select(Service)
            .where(
                Service.clinic_id == clinic.id,
                Service.is_active.is_(True),
            )
            .order_by(Service.public_name, Service.id)
        )
    )
    knowledge_items = tuple(
        session.scalars(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.clinic_id == clinic.id,
                KnowledgeItem.is_active.is_(True),
            )
            .order_by(
                KnowledgeItem.priority.desc(),
                KnowledgeItem.title,
                KnowledgeItem.id,
            )
        )
    )
    google_calendar_connected = (
        session.scalar(
            select(GoogleCredential.id).where(GoogleCredential.clinic_id == clinic.id)
        )
        is not None
    )
    workers_with_calendar = tuple(
        worker.name for worker in workers if worker.calendar_id
    )
    workers_without_calendar = tuple(
        worker.name for worker in workers if not worker.calendar_id
    )
    bookable_services = tuple(
        service.public_name for service in services if service.is_bookable_by_bot
    )
    active_conversation_flow = (
        session.scalar(
            select(ConversationFlow).where(
                ConversationFlow.id == assistant_config.conversation_flow_id,
                ConversationFlow.clinic_id == clinic.id,
                ConversationFlow.is_active.is_(True),
            )
        )
        if assistant_config.conversation_flow_id is not None
        else None
    )
    return ClinicContext(
        clinic=clinic,
        phone_number=phone_number,
        active_assistant_config=assistant_config,
        workers=workers,
        services=services,
        knowledge_items=knowledge_items,
        active_conversation_flow=active_conversation_flow,
        calendar_settings=CalendarSettings(
            timezone=clinic.timezone,
            google_calendar_connected=google_calendar_connected,
            workers_with_calendar=workers_with_calendar,
            workers_without_calendar=workers_without_calendar,
            opening_hours=dict(clinic.opening_hours_json),
        ),
        booking_rules=BookingRules(
            max_proposed_slots=3,
            verbal_confirmation_required=True,
            availability_recheck_required=True,
            bookable_services=bookable_services,
            booking_policy=assistant_config.booking_policy_prompt,
            cancellation_policy=assistant_config.cancellation_policy_prompt,
            transfer_policy=assistant_config.transfer_policy_prompt,
        ),
    )


def build_clinic_context(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    assistant_config_id: uuid.UUID | None = None,
) -> ClinicContext:
    """Build a context for previewing either the active or a selected config."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise ClinicContextError("Clinic not found.")

    config_statement = select(AssistantConfig).where(
        AssistantConfig.clinic_id == clinic.id
    )
    if assistant_config_id is None:
        config_statement = config_statement.where(AssistantConfig.is_active.is_(True))
    else:
        config_statement = config_statement.where(
            AssistantConfig.id == assistant_config_id
        )
    assistant_config = session.scalar(config_statement)
    if assistant_config is None:
        raise ActiveAssistantConfigMissing(
            "The clinic has no matching assistant configuration."
        )

    phone_number = session.scalar(
        select(PhoneNumber)
        .where(
            PhoneNumber.clinic_id == clinic.id,
            PhoneNumber.is_active.is_(True),
        )
        .order_by(
            (PhoneNumber.phone_number == clinic.main_phone_number).desc(),
            PhoneNumber.created_at,
        )
    )
    return _load_clinic_context(
        session,
        clinic=clinic,
        phone_number=phone_number,
        assistant_config=assistant_config,
    )


def resolve_clinic_by_called_number(
    called_number: str,
    session: Session | None = None,
) -> ClinicContext:
    """Resolve one active PhoneNumber and its active clinic configuration."""
    if session is None:
        with get_session_factory()() as owned_session:
            return resolve_clinic_by_called_number(
                called_number,
                session=owned_session,
            )

    candidates = _called_number_candidates(called_number)
    if not candidates:
        raise UnknownCalledNumber("The called number is missing.")
    phone_number = session.scalar(
        select(PhoneNumber)
        .join(Clinic, PhoneNumber.clinic_id == Clinic.id)
        .where(
            PhoneNumber.phone_number.in_(candidates),
            PhoneNumber.is_active.is_(True),
            Clinic.is_active.is_(True),
        )
        .order_by(PhoneNumber.created_at)
    )
    if phone_number is None:
        raise UnknownCalledNumber("No active clinic matches the called number.")
    assistant_config = session.scalar(
        select(AssistantConfig).where(
            AssistantConfig.clinic_id == phone_number.clinic_id,
            AssistantConfig.is_active.is_(True),
        )
    )
    if assistant_config is None:
        raise ActiveAssistantConfigMissing(
            "The clinic has no active assistant configuration."
        )
    return _load_clinic_context(
        session,
        clinic=phone_number.clinic,
        phone_number=phone_number,
        assistant_config=assistant_config,
    )


def _clean(value: str | None) -> str:
    """Normalize configured prose and remove control characters."""
    if not value:
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value).strip()


def _render_hours(hours: dict[str, Any]) -> str:
    """Render weekly opening or worker hours without exposing internal data."""
    if not hours:
        return "No configurado."
    lines: list[str] = []
    for day, ranges in hours.items():
        if not isinstance(ranges, list) or not ranges:
            continue
        rendered_ranges: list[str] = []
        for item in ranges:
            if not isinstance(item, dict):
                continue
            start = item.get("start")
            end = item.get("end")
            if isinstance(start, str) and isinstance(end, str):
                rendered_ranges.append(f"{start}-{end}")
        if rendered_ranges:
            lines.append(f"{day}: {', '.join(rendered_ranges)}")
    return "; ".join(lines) if lines else "No configurado."


def render_service_price(service: Service) -> str:
    """Render only configured price information."""
    if service.price_text:
        return _clean(service.price_text)
    if service.price_amount is not None:
        amount = Decimal(service.price_amount)
        return f"{amount:.2f} {service.currency}"
    return (
        "Precio no especificado; indica que consulte con recepción. "
        "No inventes un precio."
    )


def _service_worker_names(
    service: Service,
    workers_by_id: dict[str, Worker],
) -> str:
    """Render configured worker restrictions as public names."""
    if service.allowed_worker_ids is None:
        return "cualquier trabajador disponible"
    names = [
        workers_by_id[worker_id].name
        for worker_id in service.allowed_worker_ids
        if worker_id in workers_by_id
    ]
    return ", ".join(names) if names else "ningún trabajador configurado"


def build_realtime_instructions(context: ClinicContext) -> str:
    """Render the complete tenant-specific prompt without secrets or tokens."""
    clinic = context.clinic
    config = context.active_assistant_config
    workers_by_id = {str(worker.id): worker for worker in context.workers}

    service_lines = []
    for service in context.services:
        booking_state = (
            "reservable por el asistente"
            if service.is_bookable_by_bot
            else "solo información; no reservar con el asistente"
        )
        description = _clean(service.description) or "Sin descripción pública."
        service_lines.append(
            f"- {service.public_name}: {description} "
            f"Duración: {service.duration_minutes} minutos. "
            f"Precio: {render_service_price(service)}. "
            f"Trabajadores: {_service_worker_names(service, workers_by_id)}. "
            f"Estado: {booking_state}."
        )
    if not service_lines:
        service_lines.append("- No hay servicios activos configurados.")

    worker_lines = []
    for worker in context.workers:
        description = _clean(worker.public_description)
        detail = f" ({description})" if description else ""
        calendar_state = (
            "calendario disponible"
            if worker.calendar_id
            else "sin calendario; no ofrecer huecos"
        )
        worker_lines.append(
            f"- {worker.name}, {worker.role}{detail}. "
            f"Horario: {_render_hours(worker.working_hours_json)}. "
            f"{calendar_state}."
        )
    if not worker_lines:
        worker_lines.append("- No hay trabajadores activos configurados.")

    knowledge_lines = [
        f"- [{item.category.value}] {item.title}: {_clean(item.content)}"
        for item in context.knowledge_items
    ]
    if not knowledge_lines:
        knowledge_lines.append("- No hay elementos activos.")

    practical_lines = [
        f"- Teléfono público: {clinic.main_phone_number}.",
        f"- Zona horaria: {clinic.timezone}.",
        f"- Horario general: {_render_hours(clinic.opening_hours_json)}.",
    ]
    if clinic.address:
        practical_lines.append(f"- Dirección: {_clean(clinic.address)}.")
    if clinic.website:
        practical_lines.append(f"- Web: {_clean(clinic.website)}.")
    if clinic.email:
        practical_lines.append(f"- Email: {_clean(clinic.email)}.")
    if clinic.description:
        practical_lines.append(f"- Descripción: {_clean(clinic.description)}")

    calendar_summary = (
        "Google Calendar está conectado."
        if context.calendar_settings.google_calendar_connected
        else "Google Calendar no consta conectado."
    )
    linked_workers = (
        ", ".join(context.calendar_settings.workers_with_calendar) or "ninguno"
    )
    emergency_message = _clean(clinic.emergency_message) or "No configurado."
    flow_guidance = (
        render_flow_prompt(context.active_conversation_flow)
        if context.active_conversation_flow is not None
        else ""
    )

    return f"""# Identidad

Eres el asistente virtual telefónico de {clinic.name}.
Idioma principal: {config.language}.
Tono: profesional, cálido, breve, natural y adecuado para una llamada.
Debes avisar al inicio de que eres un asistente virtual.
Primer mensaje configurado: "{_clean(config.first_message)}"

# Instrucciones de la clínica

{_clean(config.system_prompt)}

# Servicios y precios

{chr(10).join(service_lines)}

# Trabajadores y horarios

{chr(10).join(worker_lines)}

# Calendarios

{calendar_summary}
Trabajadores con calendario utilizable: {linked_workers}.
Consulta siempre disponibilidad real mediante las herramientas. Un calendario
sin vincular nunca equivale a disponibilidad.

# Información práctica

{chr(10).join(practical_lines)}

# Base de conocimiento activa

{chr(10).join(knowledge_lines)}

# Política de reservas

{_clean(context.booking_rules.booking_policy)}
Propón como máximo {context.booking_rules.max_proposed_slots} horarios.
Recoge nombre, teléfono, servicio o motivo general, preferencia y trabajador
si aplica. Repite los datos y exige confirmación verbal inequívoca.
Antes de reservar, vuelve a comprobar el hueco.

# Política de cancelación

{_clean(context.booking_rules.cancellation_policy)}
Identifica la cita correcta y confirma la cancelación antes de ejecutarla.

# Política de transferencia

{_clean(context.booking_rules.transfer_policy)}

{flow_guidance}

# Seguridad médica obligatoria

{_clean(config.safety_prompt)}
No diagnostiques, no interpretes síntomas, no recomiendes medicación, dosis ni
tratamientos y no hagas triaje médico avanzado.
Si hay dolor fuerte, dificultad respiratoria, pérdida de consciencia, sangrado
grave, dolor torácico, riesgo inmediato o una situación similar, indica:
"Llame al 112 ahora o acuda a urgencias". No continúes una reserva rutinaria.
Mensaje de emergencia de la clínica: {emergency_message}

# Reglas obligatorias para herramientas

- Solo ofrece para cita los servicios marcados como reservables por el
  asistente. Los servicios de solo información pueden explicarse, pero nunca
  deben enviarse a propose_slots ni create_appointment.
- Si un servicio no tiene precio especificado, dilo claramente y recomienda
  consultar con recepción. Nunca deduzcas ni inventes un importe.
- Usa get_clinic_info cuando necesites validar información administrativa.
- Usa propose_slots para obtener hasta tres huecos reales.
- Usa check_availability antes de reservar si el hueco puede haber cambiado.
- Solo usa create_appointment tras confirmación verbal explícita.
- No afirmes que una cita está reservada hasta que create_appointment responda
  con éxito.
- Usa cancel_appointment solo después de identificar y confirmar la cita.
- Usa transfer_to_human cuando la petición quede fuera de alcance o la persona
  lo solicite.
- Usa end_call únicamente después de una despedida clara.

# Regla de veracidad estricta

Nunca inventes precios, servicios, trabajadores, políticas ni huecos.
No presentes como disponible ningún horario que no provenga de propose_slots o
check_availability. Si un dato no aparece aquí o una herramienta falla, dilo de
forma breve y ofrece transferir la llamada.
""".strip()
