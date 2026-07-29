"""Regression tests for tenant-scoped clinic statistics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.analytics_service import build_clinic_analytics
from app.models import (
    Appointment,
    AppointmentStatus,
    CallAnalysis,
    CallSession,
    CallStatus,
    Clinic,
    Service,
    Worker,
)


def test_clinic_analytics_materializes_sqlalchemy_name_rows(
    db_session: Session,
) -> None:
    clinic = Clinic(
        name="Estadísticas",
        timezone="Europe/Madrid",
        default_language="es-ES",
        main_phone_number="+34981000123",
        opening_hours_json={},
        data_retention_days=365,
        is_active=True,
    )
    db_session.add(clinic)
    db_session.flush()
    service = Service(
        clinic_id=clinic.id,
        name="Corte",
        duration_minutes=30,
        price_amount=Decimal("15.00"),
        is_active=True,
    )
    worker = Worker(
        clinic_id=clinic.id,
        name="Ana",
        role="Barbeira",
        calendar_id="analytics@calendar.test",
        is_active=True,
    )
    db_session.add_all([service, worker])
    db_session.flush()
    now = datetime.now(UTC)
    call = CallSession(
        clinic_id=clinic.id,
        openai_call_id="analytics-call",
        caller_phone="+34693694989",
        called_number=clinic.main_phone_number,
        status=CallStatus.COMPLETED,
        started_at=now - timedelta(minutes=20),
        ended_at=now - timedelta(minutes=15),
    )
    db_session.add(call)
    db_session.flush()
    appointment = Appointment(
        clinic_id=clinic.id,
        worker_id=worker.id,
        service_id=service.id,
        google_calendar_id=worker.calendar_id,
        google_event_id="analytics-event",
        patient_name="Cliente",
        patient_phone=call.caller_phone,
        start_at=now + timedelta(days=1),
        end_at=now + timedelta(days=1, minutes=30),
        status=AppointmentStatus.CONFIRMED,
        call_session_id=call.id,
    )
    analysis = CallAnalysis(
        call_session_id=call.id,
        clinic_id=clinic.id,
        sentiment_label="positive",
        sentiment_score=Decimal("0.800"),
        confidence=Decimal("0.900"),
    )
    db_session.add_all([appointment, analysis])
    db_session.commit()

    result = build_clinic_analytics(
        db_session,
        clinic=clinic,
        period="7d",
    )

    assert result.appointments_created == 1
    assert result.calls_answered == 1
    assert result.estimated_revenue_minor == 1500
    assert result.appointments_by_service[0].label == "Corte"
    assert result.appointments_by_worker[0].label == "Ana"
    assert result.sentiments[0].label == "Positivo"


def test_scheduled_filter_remains_backward_compatible(db_session: Session) -> None:
    clinic = Clinic(
        name="Filtro",
        timezone="Europe/Madrid",
        default_language="es-ES",
        main_phone_number="+34981000124",
        opening_hours_json={},
        data_retention_days=365,
        is_active=True,
    )
    db_session.add(clinic)
    db_session.commit()

    result = build_clinic_analytics(
        db_session,
        clinic=clinic,
        period="7d",
        appointment_status="scheduled",
    )
    assert result.appointments_created == 0


def test_invalid_statistics_status_returns_422(db_session: Session) -> None:
    clinic = Clinic(
        name="Filtro inválido",
        timezone="Europe/Madrid",
        default_language="es-ES",
        main_phone_number="+34981000125",
        opening_hours_json={},
        data_retention_days=365,
        is_active=True,
    )
    db_session.add(clinic)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        build_clinic_analytics(
            db_session,
            clinic=clinic,
            appointment_status="not-a-status",
        )
    assert exc.value.status_code == 422
