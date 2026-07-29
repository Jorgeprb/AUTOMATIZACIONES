"""Clinic production readiness and dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin_schemas import (
    ClinicDashboardResponse,
    DashboardLastCall,
    SetupStatusItem,
    SetupStatusResponse,
)
from app.api.admin.common import clinic_or_404
from app.db import get_db
from app.models import (
    Appointment,
    AppointmentStatus,
    AssistantConfig,
    CallEvent,
    CallSession,
    CallStatus,
    GoogleCredential,
    KnowledgeItem,
    PhoneNumber,
    Service,
    TestSession,
    Worker,
)

router = APIRouter(prefix="/admin")


def _item(
    clinic_id: uuid.UUID,
    *,
    key: str,
    label: str,
    completed: bool,
    suffix: str,
    help_text: str,
) -> SetupStatusItem:
    """Build one tenant-scoped checklist link."""
    path = f"/clinics/{clinic_id}"
    if suffix:
        path = f"{path}/{suffix}"
    return SetupStatusItem(
        key=key,
        label=label,
        completed=completed,
        href=path,
        help=help_text,
    )


def _has_completed_simulation(
    session: Session,
    clinic_id: uuid.UUID,
) -> bool:
    """Return true after one user/assistant browser test exchange."""
    message_sets = session.scalars(
        select(TestSession.messages_json).where(TestSession.clinic_id == clinic_id)
    )
    return any(len(messages) >= 3 for messages in message_sets)


def _configured_sip_target(value: str | None) -> bool:
    """Reject empty and obvious demonstration SIP targets."""
    normalized = (value or "").strip().casefold()
    return bool(normalized) and not any(
        marker in normalized for marker in ("replace", "proj_demo")
    )


def _public_webhook(value: str | None) -> bool:
    """Require a non-placeholder public HTTPS webhook URL."""
    normalized = (value or "").strip()
    if not normalized.startswith("https://"):
        return False
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").casefold()
    return bool(host) and not (
        host in {"localhost", "127.0.0.1"}
        or host.endswith((".example.com", ".example.test"))
        or "replace" in host
    )


def build_setup_status(
    session: Session,
    clinic_id: uuid.UUID,
) -> SetupStatusResponse:
    """Calculate production readiness from persisted clinic evidence."""
    clinic = clinic_or_404(session, clinic_id)
    phones = list(
        session.scalars(
            select(PhoneNumber).where(
                PhoneNumber.clinic_id == clinic_id,
                PhoneNumber.is_active.is_(True),
            )
        )
    )
    workers = list(
        session.scalars(
            select(Worker).where(
                Worker.clinic_id == clinic_id,
                Worker.is_active.is_(True),
            )
        )
    )
    services = list(
        session.scalars(
            select(Service).where(
                Service.clinic_id == clinic_id,
                Service.is_active.is_(True),
            )
        )
    )
    knowledge_count = (
        session.scalar(
            select(func.count())
            .select_from(KnowledgeItem)
            .where(
                KnowledgeItem.clinic_id == clinic_id,
                KnowledgeItem.is_active.is_(True),
            )
        )
        or 0
    )
    active_config = session.scalar(
        select(AssistantConfig).where(
            AssistantConfig.clinic_id == clinic_id,
            AssistantConfig.is_active.is_(True),
        )
    )
    google_connected = (
        session.scalar(
            select(GoogleCredential.id).where(GoogleCredential.clinic_id == clinic_id)
        )
        is not None
    )
    real_call_tested = (
        session.scalar(
            select(CallSession.id)
            .where(
                CallSession.clinic_id == clinic_id,
                CallSession.openai_call_id.not_like("simulation-%"),
            )
            .limit(1)
        )
        is not None
    )

    basic_complete = all(
        (
            clinic.name.strip(),
            clinic.timezone.strip(),
            clinic.default_language.strip(),
            clinic.main_phone_number.strip(),
            (clinic.address or "").strip(),
            (clinic.email or "").strip(),
            (clinic.emergency_message or "").strip(),
            clinic.opening_hours_json,
        )
    )
    phone_configured = any(
        phone.phone_number.strip() and _configured_sip_target(phone.sip_target)
        for phone in phones
    )
    calendars_linked = bool(workers) and all(
        (worker.calendar_id or "").strip() for worker in workers
    )
    prices_or_context = bool(knowledge_count) or (
        bool(services)
        and all(
            service.price_text or service.price_amount is not None
            for service in services
        )
    )
    prompt_reviewed = active_config is not None and all(
        (
            active_config.first_message.strip(),
            active_config.system_prompt.strip(),
            active_config.safety_prompt.strip(),
            active_config.booking_policy_prompt.strip(),
            active_config.cancellation_policy_prompt.strip(),
            active_config.transfer_policy_prompt.strip(),
        )
    )
    webhook_configured = any(_public_webhook(phone.webhook_url) for phone in phones)

    items = [
        _item(
            clinic_id,
            key="clinic_basics",
            label="Datos básicos de clínica completos",
            completed=basic_complete,
            suffix="",
            help_text=(
                "Completa contacto, dirección, horario general y mensaje de emergencia."
            ),
        ),
        _item(
            clinic_id,
            key="phone_number",
            label="Número de teléfono añadido",
            completed=phone_configured,
            suffix="",
            help_text="Añade un número activo y su destino SIP.",
        ),
        _item(
            clinic_id,
            key="google_calendar",
            label="Google Calendar conectado",
            completed=google_connected,
            suffix="calendar",
            help_text="Autoriza la cuenta Google única de la clínica.",
        ),
        _item(
            clinic_id,
            key="workers",
            label="Trabajadores creados",
            completed=bool(workers),
            suffix="workers",
            help_text="Crea al menos un trabajador activo.",
        ),
        _item(
            clinic_id,
            key="worker_calendars",
            label="Calendarios enlazados",
            completed=calendars_linked,
            suffix="calendar",
            help_text="Cada trabajador activo necesita un calendar_id.",
        ),
        _item(
            clinic_id,
            key="services",
            label="Servicios creados",
            completed=bool(services),
            suffix="services",
            help_text="Crea al menos un servicio activo.",
        ),
        _item(
            clinic_id,
            key="prices_context",
            label="Precios y contexto cargados",
            completed=prices_or_context,
            suffix="knowledge",
            help_text="Añade precios claros o información activa para el asistente.",
        ),
        _item(
            clinic_id,
            key="assistant_config",
            label="AssistantConfig activo",
            completed=active_config is not None,
            suffix="assistant",
            help_text="Activa una única configuración del asistente.",
        ),
        _item(
            clinic_id,
            key="prompt_reviewed",
            label="Prompt revisado",
            completed=prompt_reviewed,
            suffix="assistant",
            help_text="Revisa identidad, seguridad, reservas y transferencias.",
        ),
        _item(
            clinic_id,
            key="simulation_tested",
            label="Prueba simulada realizada",
            completed=_has_completed_simulation(session, clinic_id),
            suffix="test",
            help_text="Completa al menos un turno en la consola de prueba.",
        ),
        _item(
            clinic_id,
            key="public_webhook",
            label="Webhook público configurado",
            completed=webhook_configured,
            suffix="",
            help_text="Guarda una URL HTTPS pública para el webhook OpenAI.",
        ),
        _item(
            clinic_id,
            key="real_call_tested",
            label="Llamada real probada",
            completed=real_call_tested,
            suffix="conversations",
            help_text="Haz una llamada real y comprueba que aparece en conversaciones.",
        ),
    ]

    by_key = {item.key: item for item in items}
    blocking_keys = (
        "clinic_basics",
        "phone_number",
        "google_calendar",
        "workers",
        "worker_calendars",
        "services",
        "assistant_config",
        "public_webhook",
    )
    blocking_errors = [
        by_key[key].label for key in blocking_keys if not by_key[key].completed
    ]
    warnings = [
        item.label
        for item in items
        if not item.completed and item.key not in blocking_keys
    ]
    if not clinic.is_active:
        blocking_errors.append("La clínica está inactiva.")
    if services and any(
        not service.price_text and service.price_amount is None for service in services
    ):
        warnings.append("Hay servicios activos sin precio configurado.")

    return SetupStatusResponse(
        clinic_id=clinic_id,
        completed=clinic.is_active and all(item.completed for item in items),
        items=items,
        warnings=list(dict.fromkeys(warnings)),
        blocking_errors=list(dict.fromkeys(blocking_errors)),
    )


@router.get(
    "/clinics/{clinic_id}/setup-status",
    response_model=SetupStatusResponse,
    tags=["Admin · Dashboard"],
)
def get_setup_status(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> SetupStatusResponse:
    """Return the production setup checklist for one clinic."""
    return build_setup_status(session, clinic_id)


@router.get(
    "/clinics/{clinic_id}/dashboard",
    response_model=ClinicDashboardResponse,
    tags=["Admin · Dashboard"],
)
def get_dashboard(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> ClinicDashboardResponse:
    """Return lightweight operational statistics for the clinic dashboard."""
    setup = build_setup_status(session, clinic_id)
    now = datetime.now(UTC)
    last_24h = now - timedelta(hours=24)
    next_30_days = now + timedelta(days=30)
    real_call = CallSession.openai_call_id.not_like("simulation-%")

    active_workers = (
        session.scalar(
            select(func.count())
            .select_from(Worker)
            .where(
                Worker.clinic_id == clinic_id,
                Worker.is_active.is_(True),
            )
        )
        or 0
    )
    bookable_services = (
        session.scalar(
            select(func.count())
            .select_from(Service)
            .where(
                Service.clinic_id == clinic_id,
                Service.is_active.is_(True),
                Service.is_bookable_by_bot.is_(True),
            )
        )
        or 0
    )
    calls_last_24h = (
        session.scalar(
            select(func.count())
            .select_from(CallSession)
            .where(
                CallSession.clinic_id == clinic_id,
                real_call,
                CallSession.started_at >= last_24h,
            )
        )
        or 0
    )
    upcoming_appointments = (
        session.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.clinic_id == clinic_id,
                Appointment.start_at >= now,
                Appointment.start_at <= next_30_days,
                Appointment.status.in_(
                    [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]
                ),
            )
        )
        or 0
    )
    failed_calls = (
        session.scalar(
            select(func.count())
            .select_from(CallSession)
            .where(
                CallSession.clinic_id == clinic_id,
                real_call,
                CallSession.started_at >= last_24h,
                CallSession.status == CallStatus.FAILED,
            )
        )
        or 0
    )
    error_events = (
        session.scalar(
            select(func.count())
            .select_from(CallEvent)
            .join(CallSession, CallEvent.call_session_id == CallSession.id)
            .where(
                CallSession.clinic_id == clinic_id,
                real_call,
                CallEvent.created_at >= last_24h,
                or_(
                    CallEvent.event_type.ilike("%error%"),
                    CallEvent.event_type.ilike("%failed%"),
                ),
            )
        )
        or 0
    )
    last_call = session.scalar(
        select(CallSession)
        .where(CallSession.clinic_id == clinic_id, real_call)
        .order_by(CallSession.started_at.desc(), CallSession.id.desc())
        .limit(1)
    )
    phone_number_configured = session.scalar(
        select(PhoneNumber.id)
        .where(
            PhoneNumber.clinic_id == clinic_id,
            PhoneNumber.is_active.is_(True),
            PhoneNumber.sip_target.is_not(None),
            PhoneNumber.sip_target != "",
            ~PhoneNumber.sip_target.ilike("%replace%"),
            ~PhoneNumber.sip_target.ilike("%proj_demo%"),
        )
        .limit(1)
    )
    assistant_active = session.scalar(
        select(AssistantConfig.id)
        .where(
            AssistantConfig.clinic_id == clinic_id,
            AssistantConfig.is_active.is_(True),
        )
        .limit(1)
    )
    google_connected = session.scalar(
        select(GoogleCredential.id)
        .where(GoogleCredential.clinic_id == clinic_id)
        .limit(1)
    )

    return ClinicDashboardResponse(
        clinic_id=clinic_id,
        configuration_complete=setup.completed,
        google_calendar_connected=google_connected is not None,
        phone_number_configured=phone_number_configured is not None,
        assistant_active=assistant_active is not None,
        active_workers=active_workers,
        bookable_services=bookable_services,
        calls_last_24h=calls_last_24h,
        upcoming_appointments=upcoming_appointments,
        recent_errors=failed_calls + error_events,
        last_call=(
            DashboardLastCall.model_validate(last_call, from_attributes=True)
            if last_call is not None
            else None
        ),
    )
