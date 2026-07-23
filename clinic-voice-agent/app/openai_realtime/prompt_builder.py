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
from app.conversation_policy import conversation_policy_from_config
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
from app.voice_profile import build_voice_instruction_block


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
            max_proposed_slots=assistant_config.max_proposed_slots,
            verbal_confirmation_required=assistant_config.natural_confirmation_required,
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
    tone = _clean(config.tone) or "profesional"
    response_length = _clean(config.response_length) or "normal"
    max_slots = max(1, min(int(config.max_proposed_slots), 10))
    conversation_policy = conversation_policy_from_config(config)
    voice_instruction_block = build_voice_instruction_block(config)

    service_lines = []
    for service in context.services:
        booking_state = (
            "reservable por el asistente"
            if service.is_bookable_by_bot
            else "solo información; no reservar con el asistente"
        )
        description = _clean(service.description) or "Sin descripción pública."
        price = (
            render_service_price(service)
            if config.use_prices and config.allow_price_answers
            else "Uso de precios desactivado; no menciones precios."
        )
        service_lines.append(
            f"- {service.public_name}: service_id real={service.id}. "
            f"{description} "
            f"Duración: {service.duration_minutes} minutos. "
            f"Precio: {price}. "
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
            f"calendario disponible; worker_id real={worker.id}"
            if worker.calendar_id
            else "sin calendar_id; no ofrecer huecos ni reservar automáticamente"
        )
        worker_lines.append(
            f"- {worker.name}, {worker.role}{detail}. "
            f"Horario: {_render_hours(worker.working_hours_json)}. "
            f"{calendar_state}."
        )
    if not worker_lines:
        worker_lines.append("- No hay trabajadores activos configurados.")

    knowledge_lines = (
        [
            f"- [{item.category.value}] {item.title}: {_clean(item.content)}"
            for item in context.knowledge_items
        ]
        if config.use_knowledge_base
        else ["- Base de conocimiento desactivada para este asistente."]
    )
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
    emergency_message = (
        _clean(config.emergency_message)
        or _clean(clinic.emergency_message)
        or "No configurado."
    )
    no_availability_message = (
        _clean(config.no_availability_message)
        or "No tengo huecos disponibles en esa franja; te propongo alternativas."
    )
    missing_calendar_message = (
        _clean(config.missing_calendar_message)
        or "Falta enlazar el calendario del trabajador; recepción debe revisarlo."
    )
    human_transfer_message = (
        _clean(config.human_transfer_message)
        or (
            "Ahora mismo no tengo la transferencia configurada, "
            "pero dejo anotada la petición."
        )
    )
    closing_message = (
        _clean(config.closing_message) or "Gracias por llamar. Hasta luego."
    )
    human_transfer_rules = (
        _clean(config.human_transfer_rules)
        or "Transfiere si el usuario lo pide o si la petición queda fuera de alcance."
    )
    commercial_call_message = (
        _clean(config.commercial_call_message)
        or (
            "Gracias, pero este número es para pacientes y gestión de citas. "
            "No podemos atender llamadas comerciales por esta vía."
        )
    )
    additional_instructions = _clean(config.additional_instructions)
    forbidden_phrases = _clean(config.forbidden_phrases)
    conversation_extra_rules = _clean(config.conversation_extra_rules)
    ask_phone_rule = (
        "sí"
        if config.ask_patient_phone
        else "solo confirmar si caller ID ya sirve"
    )
    allow_worker_rule = (
        "sí" if config.allow_booking_without_worker else "no"
    )
    natural_confirmation_rule = (
        "sí" if config.natural_confirmation_required else "no"
    )
    price_usage = (
        "activado"
        if config.use_prices and config.allow_price_answers
        else "desactivado; no menciones precios"
    )
    knowledge_usage = (
        "activado" if config.use_knowledge_base else "desactivado"
    )
    strict_calendar_usage = (
        "activado" if config.strict_calendar_mode else "desactivado"
    )
    call_audio_lines = [
        f"- Modo de llamada: {config.call_audio_mode}.",
        f"- Proveedor de voz: {config.voice_provider}.",
        f"- Voz Realtime OpenAI: {config.realtime_voice}.",
        f"- Voz externa/ID: {_clean(config.voice_id) or 'no configurada'}.",
        f"- Modelo TTS externo: {_clean(config.tts_model) or 'no configurado'}.",
        f"- Formato audio salida: {config.output_audio_format}.",
        f"- Codec telefónico: {config.telephony_codec}.",
        (
            "- El locale, género y nombre técnico de la voz son metadatos de "
            "síntesis y no determinan el idioma de respuesta."
        ),
    ]
    if config.voice_provider != "openai":
        call_audio_lines.append(
            "- Las voces externas requieren VPS Media Bridge; no son válidas "
            "con OpenAI Hosted SIP. No prometas una voz externa si la llamada "
            "entra por OpenAI Hosted SIP."
        )
    else:
        call_audio_lines.append(
            "- Proveedor OpenAI: puede funcionar con OpenAI Hosted SIP o con "
            "VPS Media Bridge si se configura así."
        )
    flow_guidance = (
        render_flow_prompt(context.active_conversation_flow)
        if context.active_conversation_flow is not None
        else ""
    )

    return f"""# Identidad

Eres el asistente virtual telefónico de {clinic.name}.
Idioma principal obligatorio: {config.language}.
Responde en ese idioma durante toda la llamada, salvo petición expresa del usuario.
El locale o nombre técnico de la voz no cambia el idioma de conversación.
Tono configurado: {tone}. Longitud de respuesta: {response_length}.
Habla de forma natural, breve y comercial cuando encaje, adecuada para una llamada.
{"El gateway reproduce el saludo externamente. No lo repitas ni vuelvas a presentarte." if config.call_audio_mode == "vps_media_bridge" and config.voice_provider != "openai" else "Debes avisar al inicio de que eres un asistente virtual."}
Primer mensaje configurado: "{_clean(config.first_message)}"

{voice_instruction_block}

# Arquitectura de audio de llamada

{chr(10).join(call_audio_lines)}

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

# Comportamiento conversacional

Estilo conversacional: {conversation_policy.style}.
Nivel de iniciativa: {conversation_policy.initiative_level}.
Máximo de preguntas seguidas antes de resumir o proponer siguiente paso:
{conversation_policy.max_consecutive_questions}.
Reservas permitidas: {"sí" if conversation_policy.allow_bookings else "no"}.
Cancelaciones permitidas: {"sí" if conversation_policy.allow_cancellations else "no"}.
Cambios de cita permitidos: {"sí" if conversation_policy.allow_reschedules else "no"}.
Responder precios: {"sí" if conversation_policy.allow_price_answers else "no"}.
Pedir servicio como dato obligatorio:
{"sí" if conversation_policy.ask_service else "no"}.
Llamadas comerciales/spam: {conversation_policy.commercial_call_handling}.
Mensaje para llamada comercial/spam: {commercial_call_message}
Cuándo transferir a humano: {human_transfer_rules}
Reglas adicionales de conversación: {conversation_extra_rules or "No configuradas."}
Mantén estado interno con intent, service, worker, preferred_date/time,
pending_slots, selected_slot, patient_name, patient_phone, appointment_id,
awaiting_confirmation y last_user_acceptance. No repitas preguntas si el dato
ya está dado. Usa pending_slots para interpretar "a las 9", "la primera",
"esa" o "me va bien". Gestiona naturalmente información, precios, servicios,
FAQs, reservas, cancelaciones, cambios, transferencia, spam, urgencias y cierre.

{_clean(context.booking_rules.booking_policy)}
Propón como máximo {max_slots} horarios.
Pedir nombre: {"sí" if config.ask_patient_name else "no, salvo que sea necesario"}.
Pedir teléfono: {ask_phone_rule}.
Pedir motivo general: {"sí" if config.ask_general_reason else "no obligatorio"}.
Permitir reserva sin trabajador concreto: {allow_worker_rule}.
Permitir cambios de cita: {"sí" if config.allow_reschedules else "no"}.
Si no hay disponibilidad, usa este mensaje base: {no_availability_message}
Si falta calendario, usa este mensaje base: {missing_calendar_message}
Si el paciente acepta un hueco de forma natural ("sí", "vale", "perfecto",
"a las 9", "me va bien", "resérvala", "confirmo", "sí, quiero esa"), eso cuenta
como aceptación.
Confirmación natural requerida antes de reservar: {natural_confirmation_rule}.
No pedir frases exactas: {"sí" if config.avoid_exact_confirmation_phrases else "no"}.
No pidas frases exactas ni confirmaciones repetidas.
No pidas confirmaciones repetidas. Si faltan nombre o teléfono, pídelos de forma
breve. Antes de reservar, comprueba el hueco una vez.

# Política de cancelación

{_clean(context.booking_rules.cancellation_policy)}
Cancelaciones permitidas: {"sí" if config.allow_cancellations else "no"}.
Identifica la cita correcta y confirma la cancelación antes de ejecutarla.

# Política de transferencia

{_clean(context.booking_rules.transfer_policy)}
Mensaje de transferencia configurado: {human_transfer_message}

{flow_guidance}

# Seguridad médica obligatoria

{_clean(config.safety_prompt)}
No diagnostiques, no interpretes síntomas, no recomiendes medicación, dosis ni
tratamientos y no hagas triaje médico avanzado.
Si hay dolor fuerte, dificultad respiratoria, pérdida de consciencia, sangrado
grave, dolor torácico, riesgo inmediato o una situación similar, indica:
"Llame al 112 ahora o acuda a urgencias". No continúes una reserva rutinaria.
Mensaje de emergencia de la clínica: {emergency_message}

# Configuración avanzada

Uso de precios: {price_usage}.
Uso de base de conocimiento: {knowledge_usage}.
Modo estricto de calendario: {strict_calendar_usage}.
Transcripción: {"activada" if config.transcript_enabled else "desactivada"}.
Mensaje de cierre: {closing_message}
Instrucciones adicionales: {additional_instructions or "No configuradas."}
Palabras o frases prohibidas: {forbidden_phrases or "No configuradas."}

# Reglas obligatorias para herramientas

- Solo ofrece para cita los servicios marcados como reservables por el
  asistente. Los servicios de solo información pueden explicarse, pero nunca
  deben enviarse a propose_slots ni create_appointment.
- Si un servicio no tiene precio especificado, dilo claramente y recomienda
  consultar con recepción. Nunca deduzcas ni inventes un importe.
- Usa get_clinic_info cuando necesites validar información administrativa.
- Usa propose_slots para obtener hasta tres huecos reales.
- Al usar propose_slots, si conoces el servicio envía service_id y no envíes
  duration_minutes; usa duration_minutes solo cuando no tengas service_id.
- Nunca inventes worker_id ni service_id. Usa solo IDs reales listados arriba o
  envía worker_name/service_name para que el servidor los resuelva.
- No uses trabajadores sin calendar_id para reservas automáticas. Si no hay
  trabajadores con calendar_id, explica que falta asignar calendario.
- Usa check_availability solo justo antes de reservar o si el hueco puede haber
  cambiado; no lo repitas varias veces para el mismo hueco.
- Usa create_appointment cuando haya servicio, hueco/trabajador, nombre,
  teléfono y aceptación natural del paciente. Pon confirmed_by_caller=true si
  aceptó semánticamente el hueco, aunque no use una frase exacta.
- No afirmes que una cita está reservada hasta que create_appointment responda
  con éxito.
- Para mover o reprogramar una cita, identifica primero la cita actual,
  propone un nuevo hueco real, crea la nueva cita solo si hay aceptación natural
  y cancela la cita anterior solo después de que la nueva reserva tenga éxito.
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
