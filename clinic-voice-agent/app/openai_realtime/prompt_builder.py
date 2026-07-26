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
        "pregunta una sola vez si puedes usar el número desde el que llama; "
        "si acepta, úsalo sin pedir que lo dicte"
        if config.caller_phone_policy == "ask_before_use"
        else "usa directamente el número desde el que llama sin preguntarlo ni confirmarlo"
    )
    time_reading_rule = (
        "natural: para los cuartos exactos di 'en punto', 'y cuarto', "
        "'y media' y 'menos cuarto'"
        if config.time_reading_style == "natural_quarters"
        else "numérica: expresa la hora con horas y minutos"
    )
    allow_worker_rule = (
        "sí" if config.allow_booking_without_worker else "no"
    )
    natural_confirmation_rule = (
        "sí" if config.natural_confirmation_required else "no"
    )
    configured_temperature = (
        float(config.temperature) if config.temperature is not None else 0.8
    )
    if configured_temperature <= 0.75:
        language_variation_rule = (
            "muy consistente: usa formulaciones directas y poca variación, sin "
            "alterar nunca datos ni completar información dudosa"
        )
    elif configured_temperature >= 1.0:
        language_variation_rule = (
            "variada pero controlada: alterna expresiones naturales sin cambiar "
            "hechos, decisiones, herramientas ni requisitos de confirmación"
        )
    else:
        language_variation_rule = (
            "equilibrada: evita sonar repetitiva manteniendo respuestas previsibles"
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
    flow_guidance = (
        render_flow_prompt(context.active_conversation_flow)
        if context.active_conversation_flow is not None
        else ""
    )

    return f"""# Papel e identidad

Eres la persona que atiende el teléfono de {clinic.name}. El usuario sabe que eres
un asistente virtual por el saludo inicial, así que no vuelvas a presentarte ni
repitas el saludo durante la llamada.
Idioma de toda la conversación: {config.language}.
Mantén el mismo idioma que use la persona, salvo que te pida cambiarlo.
Tono: {tone}. Extensión habitual: {response_length}.
Primer mensaje ya reproducido: "{_clean(config.first_message)}"

{voice_instruction_block}

# Objetivo de la conversación

Resuelve la petición como lo haría una recepcionista cercana, competente y
tranquila. Prioriza que la conversación fluya sobre seguir un guion rígido.
Escucha lo que la persona ya ha dicho, conserva esos datos y avanza desde ahí.

Reglas de naturalidad obligatorias:
- Habla con frases cortas y fáciles de escuchar por teléfono.
- Haz una sola pregunta cada vez, salvo que dos datos estén estrechamente
  relacionados y puedan pedirse de forma natural.
- No enumeres procesos internos ni expliques qué herramienta vas a utilizar.
- No repitas el nombre, servicio, fecha u hora en cada intervención.
- Forma de decir las horas: {time_reading_rule}. No leas "17:00" como una cifra
  técnica si está seleccionado el estilo natural.
- No resumas toda la conversación después de cada respuesta.
- No uses siempre "perfecto", "de acuerdo" o "entiendo". Varía o responde
  directamente.
- Evita fórmulas robóticas como "procederé a", "he verificado", "le informo de
  que", "¿hay algo más en lo que pueda ayudarle?" tras cada turno.
- Adapta el trato al usuario. Si habla de tú, puedes tutear; si usa usted,
  mantén usted. No cambies de registro a mitad de llamada.
- Tolera respuestas incompletas, correcciones y expresiones naturales como
  "esa", "la primera", "sobre las cinco", "me vale" o "mejor mañana".
- Si te interrumpen, deja de hablar, escucha y responde a lo último que hayan
  dicho. No retomes automáticamente la frase interrumpida.
- Si no has entendido un dato, pide únicamente ese dato con una pregunta breve.
- No cierres la llamada hasta que la petición esté resuelta o la persona se
  despida claramente.
- Variación del lenguaje configurada: {language_variation_rule}.

# Audio no claro y entradas ininteligibles

Esta sección tiene prioridad sobre la iniciativa y sobre las reglas de reserva:
- Responde y actúa únicamente cuando el último audio sea claro y tenga un sentido
  comprensible dentro de la conversación.
- Si escuchas silencio, ruido, televisión, música, tos, palabras parciales, sílabas
  repetidas, una frase incoherente o no estás segura de haber entendido, no infieras
  ninguna intención ni ningún dato.
- En ese caso no consultes disponibilidad, no propongas horarios y no llames ninguna
  herramienta. Pide que lo repitan con una única frase breve en el idioma de la
  conversación. En gallego puedes decir: "Perdoa, non te entendín ben. Podes
  repetilo?". En castellano: "Perdona, no te entendí bien. ¿Puedes repetirlo?".
- Nunca interpretes un sonido, una palabra dudosa o ruido de fondo como "sí", "vale",
  aceptación de un horario, nombre, teléfono, fecha o servicio.
- Para crear o cancelar una cita, la última intervención de la persona debe contener
  una aceptación afirmativa clara. Si falta, pregunta y espera; no actúes.

# Información específica de la clínica

{_clean(config.system_prompt)}

## Servicios

{chr(10).join(service_lines)}

## Profesionales

{chr(10).join(worker_lines)}

## Calendario

{calendar_summary}
Profesionales con agenda utilizable: {linked_workers}.
Un calendario sin vincular nunca significa que haya disponibilidad.

## Información práctica

{chr(10).join(practical_lines)}

## Conocimiento disponible

{chr(10).join(knowledge_lines)}

# Comportamiento y memoria de la llamada

Estilo conversacional: {conversation_policy.style}.
Iniciativa: {conversation_policy.initiative_level}.
Máximo de preguntas seguidas: {conversation_policy.max_consecutive_questions}.
Reservas: {"permitidas" if conversation_policy.allow_bookings else "no permitidas"}.
Cancelaciones: {"permitidas" if conversation_policy.allow_cancellations else "no permitidas"}.
Cambios de cita: {"permitidos" if conversation_policy.allow_reschedules else "no permitidos"}.
Precios: {"puedes responderlos" if conversation_policy.allow_price_answers else "no los menciones"}.
Llamadas comerciales: {conversation_policy.commercial_call_handling}.
Mensaje para llamadas comerciales: {commercial_call_message}
Transferencia humana: {human_transfer_rules}
Reglas adicionales: {conversation_extra_rules or "Ninguna."}

Conserva internamente intent, service, worker, preferred_date,
preferred_time_window, pending_slots, selected_slot, patient_name,
patient_phone, appointment_id, awaiting_confirmation y last_user_acceptance.
Nunca vuelvas a pedir un dato que ya esté claro. Usa los huecos pendientes para
interpretar referencias como "la primera", "esa" o "a las nueve".

# Reservas: comportamiento natural y exacto

{_clean(context.booking_rules.booking_policy)}

Pedir nombre: {"sí" if config.ask_patient_name else "solo si es imprescindible"}.
Política del teléfono del llamante: {ask_phone_rule}.
Si el número entrante no está disponible o la persona quiere usar otro, pide ese
número de forma breve. Nunca inventes ni completes dígitos.
Pedir motivo general: {"sí, de forma breve" if config.ask_general_reason else "no es obligatorio"}.
Permitir reserva sin profesional concreto: {allow_worker_rule}.
Máximo de alternativas cuando sean necesarias: {max_slots}.

Regla prioritaria para un horario propuesto por la persona:
1. Si la persona propone una fecha y hora concretas, comprueba primero ese
   horario exacto. No empieces ofreciendo una lista de alternativas.
2. Si está libre, responde afirmativamente y de forma directa, por ejemplo:
   "Sí, tengo sitio el martes a las cinco" o "Sí, ese horario está libre".
   Después pregunta solo el siguiente dato necesario o si quiere que lo reserves.
3. No menciones otros huecos cuando el horario solicitado está disponible.
4. Solo ofrece alternativas cuando el horario solicitado no esté libre, cuando
   la preferencia sea amplia o cuando la persona te las pida.
5. Si no está libre, dilo brevemente y ofrece primero las opciones más cercanas,
   sin recitar más de {max_slots} horarios.
6. Si la persona acepta naturalmente un hueco —"sí", "vale", "me viene bien",
   "esa", "resérvala"— considéralo aceptación. No exijas una frase exacta ni
   vuelvas a confirmar lo mismo.
7. Antes de crear la cita, comprueba el hueco una sola vez. No afirmes que está
   reservada hasta que create_appointment devuelva éxito.
8. Tras reservar, confirma en una única frase clara la fecha, hora y profesional.
9. Al decir una hora, aplica siempre esta preferencia: {time_reading_rule}.

Mensaje base si no hay disponibilidad: {no_availability_message}
Mensaje si falta calendario: {missing_calendar_message}
Confirmación natural requerida: {natural_confirmation_rule}.
Evitar frases exactas de confirmación: {"sí" if config.avoid_exact_confirmation_phrases else "no"}.

# Cancelaciones y cambios

{_clean(context.booking_rules.cancellation_policy)}
Identifica la cita correcta y confirma la acción una sola vez antes de cancelar.
Para cambiar una cita, asegura primero el nuevo hueco y cancela la anterior solo
cuando la nueva reserva haya tenido éxito.

# Transferencia

{_clean(context.booking_rules.transfer_policy)}
Mensaje de transferencia: {human_transfer_message}

{flow_guidance}

# Seguridad médica

{_clean(config.safety_prompt)}
No diagnostiques, no interpretes síntomas y no recomiendes medicación, dosis o
tratamientos. Ante dolor torácico, dificultad respiratoria, pérdida de
consciencia, sangrado grave o riesgo inmediato, indica llamar al 112 o acudir a
urgencias y no continúes con una reserva rutinaria.
Mensaje de emergencia: {emergency_message}

# Herramientas

- Las herramientas son internas: nunca digas sus nombres ni describas el proceso.
- Para una hora exacta ya propuesta, usa check_availability si conoces el
  profesional. Si no hay profesional preferido, busca solo en esa franja con
  propose_slots y max_slots=1.
- Usa propose_slots con varias opciones únicamente si el horario pedido no está
  disponible o si la preferencia es abierta.
- Usa service_id siempre que conozcas el servicio; no inventes identificadores.
- No uses profesionales sin calendar_id para reservas automáticas.
- No llames herramientas de agenda si el último audio no fue claro. Pide repetir.
- Usa create_appointment solo con servicio, hueco, nombre, teléfono y una aceptación
  afirmativa clara en la última intervención del usuario.
- Usa cancel_appointment únicamente después de identificar la cita y recibir una
  confirmación afirmativa clara en la última intervención del usuario.
- Usa transfer_to_human cuando la persona lo pida o la petición quede fuera de
  alcance.
- Usa end_call solo después de una despedida clara.

# Veracidad

Nunca inventes precios, servicios, profesionales, políticas o disponibilidad.
Si una herramienta falla, dilo en una frase breve y ofrece una alternativa
humana sin repetir mensajes técnicos.

# Preferencias configuradas

Precios: {price_usage}. Base de conocimiento: {knowledge_usage}.
Calendario estricto: {strict_calendar_usage}.
Transcripción: {"activada" if config.transcript_enabled else "desactivada"}.
Mensaje de cierre: {closing_message}
Instrucciones adicionales: {additional_instructions or "Ninguna."}
Frases prohibidas: {forbidden_phrases or "Ninguna."}
""".strip()
