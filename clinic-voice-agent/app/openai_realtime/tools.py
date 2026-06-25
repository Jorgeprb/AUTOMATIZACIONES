"""OpenAI Realtime function tools for clinic voice-agent operations."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
from app.config import Settings
from app.models import CallOutcome, CallSession, Clinic, Service, Worker
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
        "parameters": parameters,
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
                required=("clinic_id",),
            ),
        ),
        _function_tool(
            "propose_slots",
            (
                "Busca huecos reales en Google Calendar y devuelve opciones "
                "ordenadas. Úsala después de conocer el servicio o duración y "
                "la preferencia del paciente. Comunica como máximo tres."
            ),
            _object_schema(
                {
                    "clinic_id": {
                        **UUID_SCHEMA,
                        "description": "UUID de la clínica de esta llamada.",
                    },
                    "service_id": {
                        **UUID_SCHEMA,
                        "description": (
                            "UUID del servicio. Usa este campo cuando el "
                            "servicio esté identificado."
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
                required=("clinic_id",),
                description=("Debe incluir exactamente service_id o duration_minutes."),
            ),
        ),
        _function_tool(
            "check_availability",
            (
                "Vuelve a comprobar un hueco exacto para un trabajador justo "
                "antes de reservar o cuando haya pasado tiempo desde la "
                "propuesta. No confirma ni crea la cita."
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
                    "service_id": {
                        **UUID_SCHEMA,
                        "description": "UUID del servicio, si aplica.",
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
                required=("clinic_id", "worker_id", "start_at", "end_at"),
            ),
        ),
        _function_tool(
            "create_appointment",
            (
                "Crea la cita definitiva. Llámala únicamente después de repetir "
                "los datos esenciales y recibir una confirmación verbal clara "
                "del paciente. Nunca la uses para comprobar disponibilidad. "
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
                    "service_id": {
                        **UUID_SCHEMA,
                        "description": "UUID del servicio, si aplica.",
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
                            "Debe ser true y solo puede enviarse tras una "
                            "confirmación verbal explícita del paciente."
                        ),
                    },
                },
                required=(
                    "clinic_id",
                    "worker_id",
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
                    required=("clinic_id",),
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
    """Inject and verify identifiers that must belong to this call."""
    trusted = dict(arguments)
    supplied_clinic_id = trusted.get("clinic_id")
    if supplied_clinic_id is not None:
        try:
            parsed_clinic_id = uuid.UUID(str(supplied_clinic_id))
        except ValueError as exc:
            raise RealtimeToolError("clinic_id no es un UUID válido.") from exc
        if parsed_clinic_id != context.clinic_id:
            raise RealtimeToolError("clinic_id no pertenece a esta llamada.")
    trusted["clinic_id"] = str(context.clinic_id)
    return trusted


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


def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    """Execute one known tool with a fresh database session."""
    trusted = _trusted_arguments(arguments, context)
    with context.session_factory() as session:
        calendar_provider = (
            context.calendar_client_provider or get_authorized_calendar_client
        )
        if name == "get_clinic_info":
            info = _clinic_info(session, context.clinic_id)
            return {"ok": True, **info.model_dump(mode="json")}

        if name == "propose_slots":
            propose_payload = AgentProposeSlotsRequest.model_validate(trusted)
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
                max_slots=min(propose_payload.max_slots, 3),
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
            return {"ok": True, **propose_response.model_dump(mode="json")}

        if name == "check_availability":
            availability_payload = AgentAvailabilityRequest.model_validate(trusted)
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
            return {
                "ok": True,
                **availability_response.model_dump(mode="json"),
            }

        if name == "create_appointment":
            if trusted.get("confirmed_by_caller") is not True:
                raise RealtimeToolError(
                    "Falta confirmación verbal explícita del paciente."
                )
            trusted.pop("confirmed_by_caller", None)
            trusted["call_session_id"] = str(context.call_session_id)
            create_payload = AgentCreateAppointmentRequest.model_validate(trusted)
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
            _mark_call_outcome(
                session,
                context,
                intent="create_appointment",
                outcome=CallOutcome.APPOINTMENT_CREATED,
            )
            return {
                "ok": True,
                **appointment_response.model_dump(mode="json"),
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
