"""Tenant-scoped analytics aggregation for one clinic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enterprise_schemas import ClinicAnalyticsResponse, MetricPoint
from app.models import (
    Appointment,
    AppointmentStatus,
    CallAnalysis,
    CallSession,
    CallStatus,
    Clinic,
    ClinicCustomer,
    Service,
    Worker,
)

_ALLOWED_PERIODS = frozenset({"today", "7d", "30d", "month", "custom"})
_WEEKDAY_LABELS = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
_STATUS_LABELS = {
    AppointmentStatus.PENDING.value: "Pendiente",
    AppointmentStatus.CONFIRMED.value: "Confirmada",
    AppointmentStatus.CANCELLED.value: "Cancelada",
    AppointmentStatus.FAILED.value: "Fallida",
    AppointmentStatus.COMPLETED.value: "Completada",
    AppointmentStatus.NO_SHOW.value: "No presentado",
    AppointmentStatus.RESCHEDULED.value: "Modificada",
}
_SENTIMENT_LABELS = {
    "positive": "Positivo",
    "neutral": "Neutral",
    "negative": "Negativo",
    "mixed": "Mixto",
    "unknown": "Sin analizar",
}


def _as_clinic_datetime(value: datetime, zone: ZoneInfo) -> datetime:
    """Interpret naive form values in the clinic timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def analytics_period(
    clinic: Clinic,
    period: str,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[datetime, datetime]:
    """Resolve a validated local period and return UTC boundaries."""
    if period not in _ALLOWED_PERIODS:
        raise HTTPException(
            status_code=422,
            detail="Periodo estadístico no válido.",
        )
    zone = ZoneInfo(clinic.timezone)
    now = datetime.now(zone)
    if date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            raise HTTPException(
                status_code=422,
                detail="El rango personalizado necesita fecha inicial y final.",
            )
        start_local = _as_clinic_datetime(date_from, zone)
        end_local = _as_clinic_datetime(date_to, zone)
        if end_local < start_local:
            raise HTTPException(
                status_code=422,
                detail="La fecha final no puede ser anterior a la inicial.",
            )
        return start_local.astimezone(UTC), end_local.astimezone(UTC)
    if period == "custom":
        raise HTTPException(
            status_code=422,
            detail="Selecciona las fechas del rango personalizado.",
        )
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=7)
    return start.astimezone(UTC), now.astimezone(UTC)


def _appointment_statuses(value: str | None) -> tuple[AppointmentStatus, ...] | None:
    if not value:
        return None
    # Backward compatibility with the first statistics frontend.
    if value == "scheduled":
        return (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED)
    try:
        return (AppointmentStatus(value),)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Estado de cita no válido.",
        ) from exc


def _counter(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _points(
    counter: dict[str, int], labels: dict[str, str] | None = None
) -> list[MetricPoint]:
    translations = labels or {}
    return [
        MetricPoint(key=key, label=translations.get(key, key), value=float(value))
        for key, value in sorted(counter.items())
    ]


def build_clinic_analytics(
    session: Session,
    *,
    clinic: Clinic,
    period: str = "7d",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    worker_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    phone_number: str | None = None,
    appointment_status: str | None = None,
) -> ClinicAnalyticsResponse:
    """Load and aggregate statistics without leaking data across clinics."""
    clinic_id = clinic.id
    start, end = analytics_period(clinic, period, date_from, date_to)
    statuses = _appointment_statuses(appointment_status)
    phone_token = phone_number.strip() if phone_number else None

    appointment_query = select(Appointment).where(
        Appointment.clinic_id == clinic_id,
        Appointment.created_at >= start,
        Appointment.created_at <= end,
    )
    if worker_id:
        appointment_query = appointment_query.where(Appointment.worker_id == worker_id)
    if service_id:
        appointment_query = appointment_query.where(Appointment.service_id == service_id)
    if phone_token:
        appointment_query = appointment_query.where(
            Appointment.patient_phone.ilike(f"%{phone_token}%")
        )
    if statuses:
        appointment_query = appointment_query.where(Appointment.status.in_(statuses))
    appointments = list(session.scalars(appointment_query))

    call_query = select(CallSession).where(
        CallSession.clinic_id == clinic_id,
        CallSession.started_at >= start,
        CallSession.started_at <= end,
    )
    if phone_token:
        call_query = call_query.where(CallSession.caller_phone.ilike(f"%{phone_token}%"))
    calls = list(session.scalars(call_query))

    # Materialise rows before constructing dictionaries. Passing SQLAlchemy's
    # ChunkedIteratorResult directly to dict() raises TypeError in SQLAlchemy 2.
    service_rows = session.execute(
        select(Service.id, Service.name, Service.price_amount).where(
            Service.clinic_id == clinic_id
        )
    ).all()
    service_names = {row_id: name for row_id, name, _price in service_rows}
    service_prices = {
        row_id: (price if price is not None else Decimal("0"))
        for row_id, _name, price in service_rows
    }
    worker_names = {
        row_id: name
        for row_id, name in session.execute(
            select(Worker.id, Worker.name).where(Worker.clinic_id == clinic_id)
        ).all()
    }

    call_ids = [call.id for call in calls]
    analyses = (
        list(
            session.scalars(
                select(CallAnalysis).where(
                    CallAnalysis.clinic_id == clinic_id,
                    CallAnalysis.call_session_id.in_(call_ids),
                )
            )
        )
        if call_ids
        else []
    )

    cancelled = sum(item.status == AppointmentStatus.CANCELLED for item in appointments)
    completed = sum(item.status == AppointmentStatus.COMPLETED for item in appointments)
    no_show = sum(item.status == AppointmentStatus.NO_SHOW for item in appointments)
    estimated_revenue_minor = sum(
        int(service_prices.get(item.service_id, Decimal("0")) * 100)
        for item in appointments
        if item.service_id is not None
        and item.status
        not in {AppointmentStatus.CANCELLED, AppointmentStatus.FAILED}
    )
    booked_call_ids = {
        item.call_session_id for item in appointments if item.call_session_id is not None
    }
    durations = [
        (call.ended_at - call.started_at).total_seconds()
        for call in calls
        if call.ended_at is not None and call.ended_at >= call.started_at
    ]

    new_customers = int(
        session.scalar(
            select(func.count(ClinicCustomer.id)).where(
                ClinicCustomer.clinic_id == clinic_id,
                ClinicCustomer.created_at >= start,
                ClinicCustomer.created_at <= end,
            )
        )
        or 0
    )
    appointment_customer_ids = {
        item.customer_id for item in appointments if item.customer_id is not None
    }
    returning_customers = 0
    if appointment_customer_ids:
        returning_customers = int(
            session.scalar(
                select(func.count(ClinicCustomer.id)).where(
                    ClinicCustomer.clinic_id == clinic_id,
                    ClinicCustomer.id.in_(appointment_customer_ids),
                    ClinicCustomer.created_at < start,
                )
            )
            or 0
        )

    zone = ZoneInfo(clinic.timezone)
    service_counter = _counter(
        [
            service_names.get(item.service_id, "Sin servicio")
            if item.service_id
            else "Sin servicio"
            for item in appointments
        ]
    )
    worker_counter = _counter(
        [worker_names.get(item.worker_id, "Sin profesional") for item in appointments]
    )
    status_counter = _counter(
        [
            str(item.status.value if hasattr(item.status, "value") else item.status)
            for item in appointments
        ]
    )
    weekday_counter = _counter(
        [_WEEKDAY_LABELS[item.start_at.astimezone(zone).weekday()] for item in appointments]
    )
    hour_counter = _counter(
        [f"{item.start_at.astimezone(zone).hour:02d}:00" for item in appointments]
    )
    timeline_counter = _counter(
        [item.created_at.astimezone(zone).date().isoformat() for item in appointments]
    )
    sentiment_counter = _counter([item.sentiment_label for item in analyses])
    heatmap_counter = _counter(
        [
            f"{item.start_at.astimezone(zone).weekday()}:{item.start_at.astimezone(zone).hour}"
            for item in appointments
        ]
    )

    return ClinicAnalyticsResponse(
        appointments_created=len(appointments),
        appointments_cancelled=cancelled,
        appointments_completed=completed,
        appointments_no_show=no_show,
        cancellation_rate=cancelled / len(appointments) if appointments else 0,
        call_to_booking_conversion=(
            len(booked_call_ids) / len(calls) if calls else 0
        ),
        estimated_revenue_minor=estimated_revenue_minor,
        calls_answered=len(calls),
        calls_failed=sum(call.status == CallStatus.FAILED for call in calls),
        average_call_duration_seconds=(
            sum(durations) / len(durations) if durations else 0
        ),
        new_customers=new_customers,
        returning_customers=returning_customers,
        appointments_by_service=_points(service_counter),
        appointments_by_worker=_points(worker_counter),
        appointments_by_weekday=_points(weekday_counter),
        appointments_by_hour=_points(hour_counter),
        appointment_statuses=_points(status_counter, _STATUS_LABELS),
        sentiments=_points(sentiment_counter, _SENTIMENT_LABELS),
        timeline=_points(timeline_counter),
        heatmap=[
            {
                "key": key,
                "value": value,
                "day": int(key.split(":", 1)[0]),
                "hour": int(key.split(":", 1)[1]),
            }
            for key, value in sorted(heatmap_counter.items())
        ],
    )
