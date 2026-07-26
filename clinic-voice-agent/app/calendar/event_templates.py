"""Safe templates for Google Calendar events created by the voice assistant."""

from __future__ import annotations

from datetime import datetime
from string import Formatter
from typing import Mapping

DEFAULT_CALENDAR_EVENT_TITLE_TEMPLATE = "Cita - {patient_name}"
DEFAULT_CALENDAR_EVENT_DESCRIPTION_TEMPLATE = """Reserva creada por asistente telefónico.
Paciente: {patient_name}
Teléfono: {patient_phone}
Servicio: {service_name}
Profesional: {worker_name}
Fecha: {start_date}
Hora: {start_time}
Motivo general: {reason}"""

CALENDAR_EVENT_TEMPLATE_FIELDS = frozenset(
    {
        "appointment_id",
        "call_session_id",
        "clinic_name",
        "patient_name",
        "patient_phone",
        "reason",
        "service_name",
        "worker_name",
        "start_date",
        "start_time",
        "end_date",
        "end_time",
        "start_datetime",
        "end_datetime",
    }
)


def validate_calendar_event_template(template: str, *, label: str) -> str:
    """Validate placeholders without allowing attribute/index traversal."""
    value = template.strip()
    if not value and label == "title":
        raise ValueError("La plantilla del título del calendario no puede estar vacía.")

    try:
        parsed = list(Formatter().parse(value))
    except ValueError as exc:
        raise ValueError(f"La plantilla de {label} contiene llaves inválidas.") from exc

    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in CALENDAR_EVENT_TEMPLATE_FIELDS:
            allowed = ", ".join(sorted(CALENDAR_EVENT_TEMPLATE_FIELDS))
            raise ValueError(
                f"Variable no permitida en la plantilla de {label}: "
                f"{{{field_name}}}. Variables disponibles: {allowed}."
            )
        if format_spec or conversion:
            raise ValueError(
                f"La variable {{{field_name}}} no admite formatos ni conversiones."
            )
    return value


def render_calendar_event_template(
    template: str,
    values: Mapping[str, object],
    *,
    label: str,
) -> str:
    """Render a prevalidated event template with bounded plain-text values."""
    validated = validate_calendar_event_template(template, label=label)
    safe_values = {
        field: str(values.get(field, "") or "")
        for field in CALENDAR_EVENT_TEMPLATE_FIELDS
    }
    return validated.format_map(safe_values).strip()


def calendar_template_values(
    *,
    appointment_id: object,
    call_session_id: object | None,
    clinic_name: str,
    patient_name: str,
    patient_phone: str,
    reason: str | None,
    service_name: str | None,
    worker_name: str,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, str]:
    """Build the documented placeholder map for one appointment."""
    return {
        "appointment_id": str(appointment_id),
        "call_session_id": str(call_session_id or ""),
        "clinic_name": clinic_name,
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "reason": reason or "No especificado",
        "service_name": service_name or "No especificado",
        "worker_name": worker_name,
        "start_date": start_at.strftime("%d/%m/%Y"),
        "start_time": start_at.strftime("%H:%M"),
        "end_date": end_at.strftime("%d/%m/%Y"),
        "end_time": end_at.strftime("%H:%M"),
        "start_datetime": start_at.strftime("%d/%m/%Y %H:%M"),
        "end_datetime": end_at.strftime("%d/%m/%Y %H:%M"),
    }
