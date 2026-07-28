"""OpenAI Realtime function tools for clinic voice-agent operations."""

from __future__ import annotations

import logging
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar.appointment_service import (
    AgentAppointmentError,
    cancel_appointment_transactional,
    check_exact_availability,
    create_appointment_transactional,
)
from app.calendar.google_client import (
    GoogleAuthorizationRequired,
    GoogleCalendarClient,
    get_authorized_calendar_client,
)
from app.calendar.scheduler import SchedulingError, propose_slots
from app.calendar.spoken_datetime import format_spoken_appointment
from app.config import Settings
from app.conversation_policy import merge_conversation_state
from app.models import (
    AssistantConfig,
    CallOutcome,
    CallSession,
    Clinic,
    Service,
    Worker,
)
from app.schemas import (
    AgentAppointmentConfirmation,
    AgentAvailabilityRequest,
    AgentAvailabilityResponse,
    AgentCancelAppointmentRequest,
    AgentCancellationConfirmation,
    AgentClinicInfoResponse,
    AgentCreateAppointmentRequest,
    AgentProposeSlotsRequest,
    AgentProposeSlotsResponse,
    AgentServiceInfo,
    AgentSlotResponse,
    AgentWorkerInfo,
)
from app.utils.privacy import MAX_GENERAL_REASON_LENGTH

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
CalendarClientProvider = Callable[
    [Session, Settings, uuid.UUID],
    GoogleCalendarClient,
]

UUID_SCHEMA: dict[str, Any] = {
    "type": "string",
    "format": "uuid",
}
DATE_SCHEMA: dict[str, Any] = {
    "type": "string",
    "format": "date",
}
DATETIME_SCHEMA: dict[str, Any] = {
    "type": "string",
    "format": "date-time",
    "description": (
        "Fecha y hora ISO 8601 con zona horaria explícita, por ejemplo "
        "2026-06-22T09:00:00+02:00."
    ),
}


def _object_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
    description: str | None = None,
) -> dict[str, Any]:
    """Build a strict JSON object schema for a Realtime function."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


REALTIME_SCHEMA_FORBIDDEN_ROOT_KEYS = {
    "oneOf",
    "anyOf",
    "allOf",
    "enum",
    "const",
    "not",
}


def _sanitize_realtime_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return a Realtime GA-compatible root JSON Schema object."""
    sanitized = {
        key: value
        for key, value in parameters.items()
        if key not in REALTIME_SCHEMA_FORBIDDEN_ROOT_KEYS
    }
    sanitized.setdefault("type", "object")
    sanitized.setdefault("properties", {})
    sanitized.setdefault("additionalProperties", False)
    return sanitized


def _function_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Build one OpenAI Realtime function-tool declaration."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": _sanitize_realtime_parameters(parameters),
    }


def get_realtime_tools() -> tuple[dict[str, Any], ...]:
    """Return the function tools available to the clinic voice assistant."""
    return (
        _function_tool(
            "get_clinic_info",
            (
                "Consulta información administrativa fiable de la clínica, "
                "incluidos servicios y trabajadores activos. Úsala antes de "
                "responder cuando no conozcas esos datos; no inventes datos."
            ),
            _object_schema(
                {
                    "clinic_id": {
                        **UUID_SCHEMA,
                        "description": "UUID de la clínica de esta llamada.",
                    }
                },
            ),
        ),
        _function_tool(
            "propose_slots",
            (
                "Busca huecos reales en Google Calendar. Si la persona ha dado "
                "una hora concreta y no ha elegido profesional, limita la búsqueda "
                "a esa franja y usa max_slots=1: si aparece libre, confirma ese "
                "horario sin ofrecer alternativas. Usa varias opciones solo cuando "
                "la preferencia sea amplia o el horario pedido no esté disponible. "
                "Si conoces el servicio, envía service_id y no duration_minutes."
            ),
            {
                **_object_schema(
                    {
                        "clinic_id": {
                            **UUID_SCHEMA,
                            "description": "UUID de la clínica de esta llamada.",
                        },
                        "service_id": {
                            **UUID_SCHEMA,
                            "description": (
                                "UUID del servicio. Usa este campo cuando el "
                                "servicio esté identificado. Si lo envías, no "
                                "envíes duration_minutes."
                            ),
                        },
                        "service_name": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Nombre público o interno del servicio cuando no "
                                "tengas service_id. El servidor lo resuelve a un "
                                "servicio real de la clínica."
                            ),
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "Duración solo cuando no exista service_id. No "
                                "envíes ambos campos."
                            ),
                        },
                        "worker_id": {
                            **UUID_SCHEMA,
                            "description": (
                                "UUID del trabajador preferido; omítelo si no hay "
                                "preferencia."
                            ),
                        },
                        "worker_name": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Nombre del trabajador preferido cuando no tengas "
                                "worker_id. No lo uses si no hay preferencia."
                            ),
                        },
                        "preferred_date": {
                            **DATE_SCHEMA,
                            "description": "Fecha local preferida, YYYY-MM-DD.",
                        },
                        "preferred_time_window": {
                            "type": "string",
                            "description": (
                                "Franja preferida: morning, afternoon, evening o "
                                "un rango HH:MM-HH:MM."
                            ),
                            "anyOf": [
                                {
                                    "enum": [
                                        "morning",
                                        "afternoon",
                                        "evening",
                                    ]
                                },
                                {
                                    "pattern": (
                                        "^([01][0-9]|2[0-3]):[0-5][0-9]-"
                                        "([01][0-9]|2[0-3]):[0-5][0-9]$"
                                    )
                                },
                            ],
                        },
                        "days_ahead": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 90,
                            "default": 14,
                            "description": "Horizonte de búsqueda en días.",
                        },
                        "max_slots": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                            "default": 3,
                            "description": "Número máximo de opciones a devolver.",
                        },
                    },
                    description=(
                        "Debe incluir service_id o duration_minutes, nunca ambos."
                    ),
                ),
                "oneOf": [
                    {"required": ["service_id"]},
                    {"required": ["service_name"]},
                    {"required": ["duration_minutes"]},
                ],
            },
        ),
        _function_tool(
            "check_availability",
            (
                "Comprueba un hueco exacto para un profesional. Úsala primero "
                "cuando la persona proponga una fecha y hora concretas. Si devuelve "
                "available=true, afirma directamente que hay sitio y no propongas "
                "alternativas. No confirma ni crea la cita."
            ),
            _object_schema(
                {
                    "clinic_id": {
                        **UUID_SCHEMA,
                        "description": "UUID de la clínica.",
                    },
                    "worker_id": {
                        **UUID_SCHEMA,
                        "description": "UUID del trabajador elegido.",
                    },
                    "worker_name": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Nombre del trabajador elegido si no tienes worker_id."
                        ),
                    },
                    "service_id": {
                        **UUID_SCHEMA,
                        "description": "UUID del servicio, si aplica.",
                    },
                    "service_name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Nombre del servicio si no tienes service_id.",
                    },
                    "start_at": {
                        **DATETIME_SCHEMA,
                        "description": ("Inicio exacto elegido, en ISO 8601 con zona."),
                    },
                    "end_at": {
                        **DATETIME_SCHEMA,
                        "description": ("Fin exacto elegido, en ISO 8601 con zona."),
                    },
                },
                required=("start_at", "end_at"),
            ),
        ),
        _function_tool(
            "create_appointment",
            (
                "Crea la cita definitiva. Llámala cuando el paciente haya "
                "aceptado de forma natural un hueco concreto y ya tengas nombre "
                "y teléfono. Nunca la uses para comprobar disponibilidad. "
                "Solo anuncia que la cita está confirmada si devuelve éxito."
            ),
            _object_schema(
                {
                    "clinic_id": {
                        **UUID_SCHEMA,
                        "description": "UUID de la clínica.",
                    },
                    "worker_id": {
                        **UUID_SCHEMA,
                        "description": "UUID del trabajador confirmado.",
                    },
                    "worker_name": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Nombre del trabajador confirmado si no tienes "
                            "worker_id."
                        ),
                    },
                    "service_id": {
                        **UUID_SCHEMA,
                        "description": "UUID del servicio, si aplica.",
                    },
                    "service_name": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Nombre del servicio confirmado si no tienes "
                            "service_id."
                        ),
                    },
                    "patient_name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Nombre confirmado del paciente.",
                    },
                    "patient_phone": {
                        "type": "string",
                        "minLength": 3,
                        "description": "Teléfono confirmado del paciente.",
                    },
                    "reason": {
                        "type": "string",
                        "maxLength": MAX_GENERAL_REASON_LENGTH,
                        "description": (
                            "Motivo general y no clínico de la cita; omítelo "
                            "si no se facilitó."
                        ),
                    },
                    "start_at": {
                        **DATETIME_SCHEMA,
                        "description": ("Inicio exacto que el paciente ha confirmado."),
                    },
                    "end_at": {
                        **DATETIME_SCHEMA,
                        "description": ("Fin exacto correspondiente al servicio."),
                    },
                    "call_session_id": {
                        **UUID_SCHEMA,
                        "description": "UUID de la sesión de llamada, si existe.",
                    },
                    "confirmed_by_caller": {
                        "type": "boolean",
                        "const": True,
                        "description": (
                            "Debe ser true cuando el paciente haya aceptado "
                            "semánticamente el hueco: sí, vale, perfecto, "
                            "a las 9, me va bien, resérvala, confirmo, etc."
                        ),
                    },
                },
                required=(
                    "patient_name",
                    "patient_phone",
                    "start_at",
                    "end_at",
                    "confirmed_by_caller",
                ),
            ),
        ),
        _function_tool(
            "cancel_appointment",
            (
                "Cancela una cita existente después de identificarla y obtener "
                "autorización verbal para cancelarla. Usa appointment_id cuando "
                "esté disponible; si no, usa teléfono y fecha aproximada."
            ),
            {
                **_object_schema(
                    {
                        "clinic_id": {
                            **UUID_SCHEMA,
                            "description": "UUID de la clínica.",
                        },
                        "appointment_id": {
                            **UUID_SCHEMA,
                            "description": "UUID de la cita identificada.",
                        },
                        "patient_phone": {
                            "type": "string",
                            "minLength": 3,
                            "description": "Teléfono usado para localizarla.",
                        },
                        "approximate_date": {
                            **DATE_SCHEMA,
                            "description": ("Fecha local aproximada de la cita."),
                        },
                    },
                ),
                "oneOf": [
                    {"required": ["appointment_id"]},
                    {
                        "required": [
                            "patient_phone",
                            "approximate_date",
                        ]
                    },
                ],
            },
        ),
        _function_tool(
            "transfer_to_human",
            (
                "Transfiere la llamada a una persona cuando el usuario lo pide, "
                "el caso queda fuera del alcance administrativo, faltan datos "
                "fiables o no puede resolverse con seguridad. En una urgencia, "
                "indica primero que llame al 112 o acuda a urgencias."
            ),
            _object_schema(
                {
                    "reason": {
                        "type": "string",
                        "enum": [
                            "user_request",
                            "medical_question",
                            "emergency",
                            "administrative_exception",
                            "technical_failure",
                            "unresolved",
                        ],
                        "description": "Motivo principal de la transferencia.",
                    },
                    "summary": {
                        "type": "string",
                        "description": (
                            "Resumen breve y no diagnóstico para la persona "
                            "que recibe la llamada."
                        ),
                    },
                },
                required=("reason",),
            ),
        ),
        _function_tool(
            "end_call",
            (
                "Finaliza la llamada solo cuando la conversación haya terminado "
                "claramente, el usuario se haya despedido o no quede ninguna "
                "acción pendiente. Despídete brevemente antes de usarla."
            ),
            _object_schema(
                {
                    "reason": {
                        "type": "string",
                        "enum": [
                            "completed",
                            "user_hangup",
                            "transferred",
                            "no_response",
                        ],
                        "description": "Motivo del cierre de la llamada.",
                    },
                    "summary": {
                        "type": "string",
                        "description": ("Resumen administrativo breve de la llamada."),
                    },
                },
                required=("reason",),
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Trusted server-side context for one Realtime call."""

    settings: Settings
    session_factory: SessionFactory
    call_session_id: uuid.UUID
    clinic_id: uuid.UUID
    openai_call_id: str
    calendar_client_provider: CalendarClientProvider | None = None
    now: datetime | None = None


class RealtimeToolError(RuntimeError):
    """Stable error safe to return to the Realtime model."""


def _trusted_arguments(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    """Inject server-trusted identifiers for this call."""
    trusted = dict(arguments)
    supplied_clinic_id = trusted.get("clinic_id")
    if supplied_clinic_id is not None:
        try:
            parsed_clinic_id = uuid.UUID(str(supplied_clinic_id))
        except ValueError:
            logger.info(
                "realtime_tool_overrode_invalid_clinic_id",
                extra={
                    "call_id": context.openai_call_id,
                    "expected_clinic_id": str(context.clinic_id),
                },
            )
        else:
            if parsed_clinic_id != context.clinic_id:
                logger.info(
                    "realtime_tool_overrode_wrong_clinic_id",
                    extra={
                        "call_id": context.openai_call_id,
                        "expected_clinic_id": str(context.clinic_id),
                        "supplied_clinic_id": str(parsed_clinic_id),
                    },
                )
    trusted["clinic_id"] = str(context.clinic_id)
    trusted["call_session_id"] = str(context.call_session_id)
    return trusted


def _sanitize_propose_slots_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Prefer the service duration over a model-supplied raw duration."""
    sanitized = dict(arguments)
    if sanitized.get("service_id"):
        sanitized.pop("duration_minutes", None)
    return sanitized


def _normalize_label(value: object) -> str:
    """Normalize public names for forgiving tool argument matching."""
    stripped = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(
        char for char in stripped if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().split())


def _safe_uuid(value: object, *, field_name: str) -> uuid.UUID:
    """Parse UUIDs received from model tools with a stable error."""
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise RealtimeToolError(
            f"{field_name} no es un UUID real válido de esta clínica. "
            "Usa un ID real del contexto o envía el nombre correspondiente."
        ) from exc


def _service_names(service: Service) -> set[str]:
    """Return all user-facing names that can identify a service."""
    return {
        value
        for value in (service.name, service.public_name)
        if isinstance(value, str) and value.strip()
    }


def _format_services(services: list[Service]) -> str:
    """Render real service choices for a safe tool error."""
    if not services:
        return "ningún servicio reservable configurado"
    return "; ".join(
        f"{service.public_name or service.name} (service_id={service.id})"
        for service in services
    )


def _format_workers(workers: list[Worker]) -> str:
    """Render real worker choices for a safe tool error."""
    if not workers:
        return "ningún trabajador activo con calendar_id"
    return "; ".join(
        f"{worker.name} (worker_id={worker.id})" for worker in workers
    )


def _bookable_services(session: Session, clinic_id: uuid.UUID) -> list[Service]:
    """Return active services that the bot may use for booking tools."""
    return list(
        session.scalars(
            select(Service)
            .where(
                Service.clinic_id == clinic_id,
                Service.is_active.is_(True),
                Service.is_bookable_by_bot.is_(True),
            )
            .order_by(Service.name)
        )
    )


def _active_workers(session: Session, clinic_id: uuid.UUID) -> list[Worker]:
    """Return active clinic workers."""
    return list(
        session.scalars(
            select(Worker)
            .where(
                Worker.clinic_id == clinic_id,
                Worker.is_active.is_(True),
            )
            .order_by(Worker.name)
        )
    )


def _resolve_service_reference(
    session: Session,
    arguments: dict[str, Any],
    *,
    clinic_id: uuid.UUID,
) -> Service | None:
    """Resolve service_name or validate service_id against this clinic."""
    service_id = arguments.get("service_id")
    services = _bookable_services(session, clinic_id)
    if service_id:
        parsed_service_id = _safe_uuid(service_id, field_name="service_id")
        service = session.get(Service, parsed_service_id)
        if (
            service is None
            or service.clinic_id != clinic_id
            or not service.is_active
            or not service.is_bookable_by_bot
        ):
            raise RealtimeToolError(
                "service_id no pertenece a esta clínica o no es reservable. "
                f"Usa uno válido: {_format_services(services)}."
            )
        arguments["service_id"] = str(service.id)
        return service

    service_name = str(arguments.get("service_name") or "").strip()
    if not service_name:
        return None
    wanted = _normalize_label(service_name)
    matches = [
        service
        for service in services
        if wanted in {_normalize_label(name) for name in _service_names(service)}
    ]
    if len(matches) == 1:
        service = matches[0]
        arguments["service_id"] = str(service.id)
        return service
    if len(matches) > 1:
        raise RealtimeToolError(
            "service_name es ambiguo. Usa service_id de una opción real: "
            f"{_format_services(matches)}."
        )
    all_active_services = list(
        session.scalars(
            select(Service)
            .where(
                Service.clinic_id == clinic_id,
                Service.is_active.is_(True),
            )
            .order_by(Service.name)
        )
    )
    non_bookable_match = next(
        (
            service
            for service in all_active_services
            if wanted in {_normalize_label(name) for name in _service_names(service)}
        ),
        None,
    )
    if non_bookable_match is not None and not non_bookable_match.is_bookable_by_bot:
        service_label = non_bookable_match.public_name or non_bookable_match.name
        raise RealtimeToolError(
            f"El servicio '{service_label}' no es reservable por el asistente. "
            "No lo uses para crear citas."
        )
    raise RealtimeToolError(
        "service_name no coincide con ningún servicio reservable de esta clínica. "
        f"Usa una opción válida: {_format_services(services)}."
    )


def _resolve_worker_reference(
    session: Session,
    arguments: dict[str, Any],
    *,
    clinic_id: uuid.UUID,
    required: bool,
) -> Worker | None:
    """Resolve worker_name or validate worker_id against linked clinic workers."""
    workers = _active_workers(session, clinic_id)
    calendar_workers = [worker for worker in workers if worker.calendar_id]
    worker_id = arguments.get("worker_id")
    if worker_id:
        parsed_worker_id = _safe_uuid(worker_id, field_name="worker_id")
        worker = session.get(Worker, parsed_worker_id)
        if worker is None or worker.clinic_id != clinic_id or not worker.is_active:
            raise RealtimeToolError(
                "worker_id no pertenece a esta clínica o está inactivo. "
                f"Usa uno válido: {_format_workers(calendar_workers)}."
            )
        if not worker.calendar_id:
            raise RealtimeToolError(
                f"El trabajador '{worker.name}' no tiene calendar_id. "
                "Asigna un calendario antes de usarlo para reservas automáticas."
            )
        arguments["worker_id"] = str(worker.id)
        return worker

    worker_name = str(arguments.get("worker_name") or "").strip()
    if worker_name:
        wanted = _normalize_label(worker_name)
        matches = [
            worker
            for worker in calendar_workers
            if _normalize_label(worker.name) == wanted
        ]
        if len(matches) == 1:
            worker = matches[0]
            arguments["worker_id"] = str(worker.id)
            return worker
        if len(matches) > 1:
            raise RealtimeToolError(
                "worker_name es ambiguo. Usa worker_id de una opción real: "
                f"{_format_workers(matches)}."
            )
        inactive_calendarless_match = next(
            (
                worker
                for worker in workers
                if _normalize_label(worker.name) == wanted and not worker.calendar_id
            ),
            None,
        )
        if inactive_calendarless_match is not None:
            raise RealtimeToolError(
                f"El trabajador '{inactive_calendarless_match.name}' no tiene "
                "calendar_id. Asigna un calendario antes de reservar con él."
            )
        raise RealtimeToolError(
            "worker_name no coincide con ningún trabajador activo con calendario. "
            f"Usa una opción válida: {_format_workers(calendar_workers)}."
        )

    if not calendar_workers:
        raise RealtimeToolError(
            "No hay trabajadores activos con calendar_id. Asigna un calendario "
            "al trabajador antes de consultar o crear citas."
        )
    if len(calendar_workers) == 1:
        worker = calendar_workers[0]
        arguments["worker_id"] = str(worker.id)
        return worker
    if required:
        raise RealtimeToolError(
            "Falta trabajador. Usa worker_name o worker_id de una opción válida: "
            f"{_format_workers(calendar_workers)}."
        )
    return None


def _validate_worker_service_pair(
    worker: Worker | None,
    service: Service | None,
) -> None:
    """Ensure an explicit worker is allowed for the selected service."""
    if worker is None or service is None or service.allowed_worker_ids is None:
        return
    allowed_worker_ids = {str(value) for value in service.allowed_worker_ids}
    if str(worker.id) not in allowed_worker_ids:
        raise RealtimeToolError(
            f"El trabajador '{worker.name}' no está permitido para el servicio "
            f"'{service.public_name or service.name}'. Elige otra opción válida."
        )


def _normalize_booking_tool_arguments(
    session: Session,
    name: str,
    arguments: dict[str, Any],
    *,
    clinic_id: uuid.UUID,
) -> dict[str, Any]:
    """Resolve model-facing names and reject fake cross-clinic IDs."""
    if name not in {"propose_slots", "check_availability", "create_appointment"}:
        return arguments
    normalized = dict(arguments)
    service = _resolve_service_reference(session, normalized, clinic_id=clinic_id)
    worker = _resolve_worker_reference(
        session,
        normalized,
        clinic_id=clinic_id,
        required=name in {"check_availability", "create_appointment"},
    )
    _validate_worker_service_pair(worker, service)
    if name == "propose_slots":
        normalized = _sanitize_propose_slots_arguments(normalized)
    return normalized


def _clinic_info(session: Session, clinic_id: uuid.UUID) -> AgentClinicInfoResponse:
    """Read active clinic resources without making external requests."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise RealtimeToolError("Clínica no encontrada.")
    workers = session.scalars(
        select(Worker)
        .where(Worker.clinic_id == clinic.id, Worker.is_active.is_(True))
        .order_by(Worker.name)
    )
    services = session.scalars(
        select(Service)
        .where(
            Service.clinic_id == clinic.id,
            Service.is_active.is_(True),
            Service.is_bookable_by_bot.is_(True),
        )
        .order_by(Service.name)
    )
    return AgentClinicInfoResponse(
        id=clinic.id,
        name=clinic.name,
        timezone=clinic.timezone,
        phone_number=clinic.phone_number,
        workers=[
            AgentWorkerInfo(
                id=worker.id,
                name=worker.name,
                role=worker.role,
                is_active=worker.is_active,
                calendar_linked=worker.calendar_id is not None,
            )
            for worker in workers
        ],
        services=[
            AgentServiceInfo(
                id=service.id,
                name=service.name,
                duration_minutes=service.duration_minutes,
                buffer_before_minutes=service.buffer_before_minutes,
                buffer_after_minutes=service.buffer_after_minutes,
            )
            for service in services
        ],
    )


def _update_call_intent(
    session: Session,
    context: ToolExecutionContext,
    *,
    values: dict[str, Any],
    summary: str | None = None,
) -> None:
    """Persist non-destructive call-control intent from a local tool."""
    call_session = session.get(CallSession, context.call_session_id)
    if call_session is None:
        raise RealtimeToolError("Sesión de llamada no encontrada.")
    state = dict(call_session.conversation_state_json)
    state.update(values)
    call_session.conversation_state_json = state
    del summary
    if values.get("handoff_requested"):
        call_session.summary_text = "Transferencia administrativa solicitada."
    elif values.get("end_call_requested"):
        call_session.summary_text = "Llamada finalizada por el asistente."
    session.commit()


def _persist_conversation_state(
    session: Session,
    context: ToolExecutionContext,
    **updates: Any,
) -> None:
    """Persist the shared ConversationState subset without losing runtime keys."""
    call_session = session.get(CallSession, context.call_session_id)
    if call_session is None:
        return
    call_session.conversation_state_json = merge_conversation_state(
        call_session.conversation_state_json,
        **updates,
    )
    session.commit()


def _mark_call_outcome(
    session: Session,
    context: ToolExecutionContext,
    *,
    intent: str,
    outcome: CallOutcome,
) -> None:
    """Persist a successful business outcome for the admin panel."""
    call_session = session.get(CallSession, context.call_session_id)
    if call_session is None:
        return
    call_session.detected_intent = intent
    call_session.outcome = outcome
    session.commit()


def _assistant_config_for_call(
    session: Session,
    context: ToolExecutionContext,
) -> AssistantConfig:
    """Resolve the immutable config attached to the current call session."""
    call_session = session.get(CallSession, context.call_session_id)
    config = (
        session.get(AssistantConfig, call_session.assistant_config_id)
        if call_session is not None and call_session.assistant_config_id is not None
        else None
    )
    if config is None:
        config = session.scalar(
            select(AssistantConfig).where(
                AssistantConfig.clinic_id == context.clinic_id,
                AssistantConfig.is_active.is_(True),
            )
        )
    if config is None:
        raise RealtimeToolError("No hay una configuración activa para esta llamada.")
    return config


def _slot_start_matches_grid(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    start_at: datetime,
    interval_minutes: int,
) -> bool:
    """Validate a requested start against the clinic-local appointment grid."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise RealtimeToolError("La clínica no existe.")
    local_start = start_at.astimezone(ZoneInfo(clinic.timezone))
    minutes_from_midnight = local_start.hour * 60 + local_start.minute
    return (
        local_start.second == 0
        and local_start.microsecond == 0
        and minutes_from_midnight % interval_minutes == 0
    )


def _availability_guidance(
    *,
    available: bool,
    direct: bool,
    spoken_start_at: str | None = None,
) -> str:
    if available:
        if direct:
            detail = f" para {spoken_start_at}" if spoken_start_at else ""
            return (
                f"Responde directamente que hay un hueco{detail}. No digas que vas "
                "a comprobarlo, que lo estás revisando ni que ya lo has comprobado. "
                "No ofrezcas alternativas."
            )
        return (
            "Puedes explicar brevemente que has comprobado la agenda y que el horario "
            "está disponible; no ofrezcas alternativas."
        )
    if direct:
        return (
            "Di directamente que ese horario no está libre. No narres la consulta de "
            "agenda y ofrece alternativas solo si la persona quiere continuar."
        )
    return (
        "Indica que la consulta de agenda no encontró ese horario y pregunta si quiere "
        "alternativas cercanas."
    )


def _booking_success_guidance(
    config: AssistantConfig,
    *,
    spoken_start_at: str,
) -> str:
    confirmation = (
        f"Confirma la reserva incluyendo exactamente la fecha y la hora natural: "
        f"{spoken_start_at}."
        if config.booking_confirmation_datetime_enabled
        else "Confirma brevemente que la cita ha quedado reservada."
    )
    direct = (
        " No digas 'voy a reservar', 'procedo a reservar' ni 'un momento'. "
        "Empieza directamente con la confirmación final."
        if config.direct_booking_response
        else " Puedes mencionar brevemente que la reserva se ha completado."
    )
    followup_message = (
        (config.post_booking_followup_message or "¿Puedo ayudarte con algo más?").strip()
    )
    followup = (
        f' Después pregunta una sola vez: "{followup_message}". Si la persona '
        "necesita algo más, ayúdala y vuelve a hacer la misma pregunta al terminar."
        if config.post_booking_followup_enabled
        else ""
    )
    closing = (
        " Si responde que no necesita nada más, di el mensaje de despedida y llama "
        "a end_call para finalizar la llamada."
        if config.post_booking_followup_enabled and config.hangup_after_no_more_help
        else ""
    )
    return confirmation + direct + followup + closing


def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    """Execute one known tool with a fresh database session."""
    trusted = _trusted_arguments(arguments, context)
    with context.session_factory() as session:
        assistant_config = _assistant_config_for_call(session, context)
        calendar_provider = (
            context.calendar_client_provider or get_authorized_calendar_client
        )
        if name == "get_clinic_info":
            info = _clinic_info(session, context.clinic_id)
            return {"ok": True, **info.model_dump(mode="json")}

        if name == "propose_slots":
            trusted = _normalize_booking_tool_arguments(
                session,
                name,
                trusted,
                clinic_id=context.clinic_id,
            )
            propose_payload = AgentProposeSlotsRequest.model_validate(
                trusted
            )
            client = calendar_provider(
                session,
                context.settings,
                propose_payload.clinic_id,
            )
            slots = propose_slots(
                session,
                client,
                clinic_id=propose_payload.clinic_id,
                service_id=propose_payload.service_id,
                duration_minutes=propose_payload.duration_minutes,
                worker_id=propose_payload.worker_id,
                preferred_date=propose_payload.preferred_date,
                preferred_time_window=propose_payload.preferred_time_window,
                days_ahead=propose_payload.days_ahead,
                max_slots=min(
                    propose_payload.max_slots,
                    assistant_config.max_proposed_slots,
                ),
                slot_interval_minutes=assistant_config.slot_interval_minutes,
                now=context.now,
            )
            propose_response = AgentProposeSlotsResponse(
                slots=[
                    AgentSlotResponse(
                        worker_id=slot.worker_id,
                        worker_name=slot.worker_name,
                        calendar_id=slot.calendar_id,
                        start_at=slot.start_at,
                        end_at=slot.end_at,
                        blocked_start_at=slot.blocked_start_at,
                        blocked_end_at=slot.blocked_end_at,
                    )
                    for slot in slots
                ]
            )
            service_state = None
            if propose_payload.service_id is not None:
                service = session.get(Service, propose_payload.service_id)
                if service is not None:
                    service_state = {
                        "id": str(service.id),
                        "name": service.public_name or service.name,
                    }
            worker_state = None
            if propose_payload.worker_id is not None:
                worker = session.get(Worker, propose_payload.worker_id)
                if worker is not None:
                    worker_state = {
                        "id": str(worker.id),
                        "name": worker.name,
                    }
            _persist_conversation_state(
                session,
                context,
                intent="create_appointment",
                service=service_state,
                worker=worker_state,
                preferred_date=(
                    propose_payload.preferred_date.isoformat()
                    if propose_payload.preferred_date
                    else None
                ),
                preferred_time_window=propose_payload.preferred_time_window,
                pending_slots=propose_response.model_dump(mode="json")["slots"],
                selected_slot=None,
                awaiting_confirmation=bool(propose_response.slots),
            )
            exact_request = propose_payload.max_slots == 1
            spoken_slots = [
                {
                    "worker_id": str(slot.worker_id),
                    "spoken_start_at": format_spoken_appointment(
                        slot.start_at,
                        assistant_config.language,
                    ),
                }
                for slot in slots
            ]
            if exact_request:
                guidance = _availability_guidance(
                    available=bool(propose_response.slots),
                    direct=assistant_config.direct_availability_response,
                    spoken_start_at=(
                        spoken_slots[0]["spoken_start_at"]
                        if spoken_slots
                        else None
                    ),
                )
            elif assistant_config.direct_availability_response:
                guidance = (
                    "Presenta directamente solo los horarios disponibles más relevantes. "
                    "No digas que vas a consultar, comprobar o revisar la agenda."
                )
            else:
                guidance = "Presenta solo las opciones más relevantes de forma natural."
            return {
                "ok": True,
                **propose_response.model_dump(mode="json"),
                "spoken_slots": spoken_slots,
                "slot_interval_minutes": assistant_config.slot_interval_minutes,
                "exact_time_request": exact_request,
                "assistant_guidance": guidance,
            }

        if name == "check_availability":
            trusted = _normalize_booking_tool_arguments(
                session,
                name,
                trusted,
                clinic_id=context.clinic_id,
            )
            availability_payload = AgentAvailabilityRequest.model_validate(trusted)
            if not _slot_start_matches_grid(
                session,
                clinic_id=availability_payload.clinic_id,
                start_at=availability_payload.start_at,
                interval_minutes=assistant_config.slot_interval_minutes,
            ):
                spoken_start_at = format_spoken_appointment(
                    availability_payload.start_at,
                    assistant_config.language,
                )
                return {
                    "ok": True,
                    "available": False,
                    "clinic_id": str(availability_payload.clinic_id),
                    "worker_id": str(availability_payload.worker_id),
                    "start_at": availability_payload.start_at.isoformat(),
                    "end_at": availability_payload.end_at.isoformat(),
                    "reason": "outside_slot_grid",
                    "spoken_start_at": spoken_start_at,
                    "slot_interval_minutes": assistant_config.slot_interval_minutes,
                    "assistant_guidance": (
                        "Ese inicio no pertenece a los horarios configurados de la "
                        f"clínica, que comienzan cada {assistant_config.slot_interval_minutes} "
                        "minutos. No lo reserves. Busca la opción válida más cercana y "
                        "respóndela de forma directa."
                    ),
                }
            client = calendar_provider(
                session,
                context.settings,
                availability_payload.clinic_id,
            )
            availability = check_exact_availability(
                session,
                client,
                clinic_id=availability_payload.clinic_id,
                worker_id=availability_payload.worker_id,
                service_id=availability_payload.service_id,
                start_at=availability_payload.start_at,
                end_at=availability_payload.end_at,
            )
            availability_response = AgentAvailabilityResponse(
                available=availability.available,
                clinic_id=availability_payload.clinic_id,
                worker_id=availability_payload.worker_id,
                start_at=availability_payload.start_at,
                end_at=availability_payload.end_at,
                reason=availability.reason,
            )
            worker = session.get(Worker, availability_payload.worker_id)
            service = (
                session.get(Service, availability_payload.service_id)
                if availability_payload.service_id is not None
                else None
            )
            _persist_conversation_state(
                session,
                context,
                intent="create_appointment",
                worker={
                    "id": str(worker.id),
                    "name": worker.name,
                }
                if worker is not None
                else None,
                service={
                    "id": str(service.id),
                    "name": service.public_name or service.name,
                }
                if service is not None
                else None,
                selected_slot={
                    "worker_id": str(availability_payload.worker_id),
                    "start_at": availability_payload.start_at.isoformat(),
                    "end_at": availability_payload.end_at.isoformat(),
                    "available": availability.available,
                },
                awaiting_confirmation=availability.available,
            )
            spoken_start_at = format_spoken_appointment(
                availability_payload.start_at,
                assistant_config.language,
            )
            return {
                "ok": True,
                **availability_response.model_dump(mode="json"),
                "spoken_start_at": spoken_start_at,
                "assistant_guidance": _availability_guidance(
                    available=availability.available,
                    direct=assistant_config.direct_availability_response,
                    spoken_start_at=spoken_start_at,
                ),
            }

        if name == "create_appointment":
            if trusted.get("confirmed_by_caller") is not True:
                raise RealtimeToolError(
                    "Falta aceptación natural del paciente para ese hueco."
                )
            trusted.pop("confirmed_by_caller", None)
            trusted["call_session_id"] = str(context.call_session_id)
            trusted = _normalize_booking_tool_arguments(
                session,
                name,
                trusted,
                clinic_id=context.clinic_id,
            )
            create_payload = AgentCreateAppointmentRequest.model_validate(trusted)
            if not _slot_start_matches_grid(
                session,
                clinic_id=create_payload.clinic_id,
                start_at=create_payload.start_at,
                interval_minutes=assistant_config.slot_interval_minutes,
            ):
                raise RealtimeToolError(
                    "La hora seleccionada no pertenece a la cuadrícula de citas "
                    f"configurada cada {assistant_config.slot_interval_minutes} minutos. "
                    "Consulta otra hora válida antes de reservar."
                )
            client = calendar_provider(
                session,
                context.settings,
                create_payload.clinic_id,
            )
            appointment = create_appointment_transactional(
                session,
                client,
                clinic_id=create_payload.clinic_id,
                worker_id=create_payload.worker_id,
                service_id=create_payload.service_id,
                patient_name=create_payload.patient_name,
                patient_phone=create_payload.patient_phone,
                reason=create_payload.reason,
                start_at=create_payload.start_at,
                end_at=create_payload.end_at,
                call_session_id=context.call_session_id,
                idempotency_key=(
                    create_payload.idempotency_key
                    or f"voice:{context.call_session_id}:{create_payload.worker_id}:"
                    f"{create_payload.start_at.isoformat()}"
                ),
            )
            appointment_response = AgentAppointmentConfirmation(
                status="confirmed",
                appointment_id=appointment.id,
                clinic_id=appointment.clinic_id,
                worker_id=appointment.worker_id,
                worker_name=appointment.worker.name,
                service_id=appointment.service_id,
                patient_name=appointment.patient_name,
                patient_phone=appointment.patient_phone,
                start_at=appointment.start_at,
                end_at=appointment.end_at,
                google_calendar_id=appointment.google_calendar_id,
                google_event_id=appointment.google_event_id,
            )
            _persist_conversation_state(
                session,
                context,
                intent="create_appointment",
                service={
                    "id": str(appointment.service_id),
                    "name": appointment.service.public_name
                    if appointment.service is not None
                    else None,
                }
                if appointment.service_id is not None
                else None,
                worker={
                    "id": str(appointment.worker_id),
                    "name": appointment.worker.name,
                },
                selected_slot={
                    "worker_id": str(appointment.worker_id),
                    "start_at": appointment.start_at.isoformat(),
                    "end_at": appointment.end_at.isoformat(),
                },
                pending_slots=[],
                patient_name=appointment.patient_name,
                patient_phone=appointment.patient_phone,
                appointment_id=str(appointment.id),
                awaiting_confirmation=False,
                last_user_acceptance="confirmed_by_caller",
            )
            _mark_call_outcome(
                session,
                context,
                intent="create_appointment",
                outcome=CallOutcome.APPOINTMENT_CREATED,
            )
            spoken_start_at = format_spoken_appointment(
                appointment.start_at,
                assistant_config.language,
            )
            return {
                "ok": True,
                **appointment_response.model_dump(mode="json"),
                "spoken_start_at": spoken_start_at,
                "post_booking_followup_enabled": (
                    assistant_config.post_booking_followup_enabled
                ),
                "post_booking_followup_message": (
                    assistant_config.post_booking_followup_message
                    or "¿Puedo ayudarte con algo más?"
                ),
                "hangup_after_no_more_help": (
                    assistant_config.hangup_after_no_more_help
                ),
                "assistant_guidance": _booking_success_guidance(
                    assistant_config,
                    spoken_start_at=spoken_start_at,
                ),
            }

        if name == "cancel_appointment":
            cancel_payload = AgentCancelAppointmentRequest.model_validate(trusted)
            client = calendar_provider(
                session,
                context.settings,
                cancel_payload.clinic_id,
            )
            appointment, already_cancelled = cancel_appointment_transactional(
                session,
                client,
                clinic_id=cancel_payload.clinic_id,
                appointment_id=cancel_payload.appointment_id,
                patient_phone=cancel_payload.patient_phone,
                approximate_date=cancel_payload.approximate_date,
            )
            cancellation_response = AgentCancellationConfirmation(
                status="already_cancelled" if already_cancelled else "cancelled",
                appointment_id=appointment.id,
                patient_name=appointment.patient_name,
                patient_phone=appointment.patient_phone,
                start_at=appointment.start_at,
                worker_id=appointment.worker_id,
                google_event_id=appointment.google_event_id,
            )
            _persist_conversation_state(
                session,
                context,
                intent="cancel_appointment",
                worker={
                    "id": str(appointment.worker_id),
                    "name": appointment.worker.name,
                }
                if appointment.worker is not None
                else None,
                service={
                    "id": str(appointment.service_id),
                    "name": appointment.service.public_name
                    if appointment.service is not None
                    else None,
                }
                if appointment.service_id is not None
                else None,
                selected_slot={
                    "worker_id": str(appointment.worker_id),
                    "start_at": appointment.start_at.isoformat(),
                },
                patient_name=appointment.patient_name,
                patient_phone=appointment.patient_phone,
                appointment_id=str(appointment.id),
                awaiting_confirmation=False,
            )
            _mark_call_outcome(
                session,
                context,
                intent="cancel_appointment",
                outcome=CallOutcome.CANCELLED,
            )
            return {
                "ok": True,
                **cancellation_response.model_dump(mode="json"),
            }

        if name == "transfer_to_human":
            _update_call_intent(
                session,
                context,
                values={
                    "intent": "transfer_to_human",
                    "handoff_requested": True,
                    "handoff_reason": trusted.get("reason"),
                },
                summary=trusted.get("summary"),
            )
            _mark_call_outcome(
                session,
                context,
                intent="transfer_to_human",
                outcome=CallOutcome.TRANSFERRED,
            )
            return {
                "ok": False,
                "status": "handoff_not_configured",
                "message": "Transferencia humana no configurada todavía.",
            }

        if name == "end_call":
            _update_call_intent(
                session,
                context,
                values={
                    "intent": "close_conversation",
                    "end_call_requested": True,
                    "end_call_reason": trusted.get("reason"),
                },
                summary=trusted.get("summary"),
            )
            return {
                "ok": True,
                "status": "end_call_requested",
                "message": "La llamada puede cerrarse tras la despedida.",
            }

    raise RealtimeToolError(f"Herramienta desconocida: {name}.")


def execute_realtime_tool(
    name: str,
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    """Dispatch one Realtime function call and return JSON-safe output."""
    try:
        return _execute_tool(name, arguments, context)
    except (
        AgentAppointmentError,
        GoogleAuthorizationRequired,
        RealtimeToolError,
        SchedulingError,
        ValidationError,
        ValueError,
    ) as exc:
        logger.warning(
            "realtime_tool_failed",
            extra={
                "call_id": context.openai_call_id,
                "tool_name": name,
                "error": str(exc),
            },
        )
        return {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }
    except Exception:
        logger.exception(
            "realtime_tool_unexpected_error",
            extra={
                "call_id": context.openai_call_id,
                "tool_name": name,
            },
        )
        return {
            "ok": False,
            "error": "internal_error",
            "message": "La herramienta falló de forma inesperada.",
        }
