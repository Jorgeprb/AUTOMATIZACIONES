"""Calendar event template safety and rendering tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.calendar.event_templates import (
    calendar_template_values,
    render_calendar_event_template,
    validate_calendar_event_template,
)


def test_calendar_template_renders_documented_fields() -> None:
    values = calendar_template_values(
        appointment_id="appointment-1",
        call_session_id="call-1",
        clinic_name="Clínica Norte",
        patient_name="María López",
        patient_phone="+34981111222",
        reason="Revisión",
        service_name="Consulta general",
        worker_name="Dra. Ana",
        start_at=datetime(2026, 7, 28, 17, 0),
        end_at=datetime(2026, 7, 28, 17, 30),
    )

    assert (
        render_calendar_event_template(
            "{service_name} - {patient_name}",
            values,
            label="title",
        )
        == "Consulta general - María López"
    )
    assert (
        render_calendar_event_template(
            "Paciente: {patient_name}\nHora: {start_time}",
            values,
            label="description",
        )
        == "Paciente: María López\nHora: 17:00"
    )


def test_calendar_template_rejects_unknown_or_traversed_fields() -> None:
    with pytest.raises(ValueError, match="Variable no permitida"):
        validate_calendar_event_template("{unknown}", label="title")
    with pytest.raises(ValueError, match="Variable no permitida"):
        validate_calendar_event_template("{patient_name.__class__}", label="title")


def test_calendar_title_cannot_be_empty() -> None:
    with pytest.raises(ValueError, match="no puede estar vacía"):
        validate_calendar_event_template("   ", label="title")
