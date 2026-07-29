"""Durable maintenance jobs executed with a PostgreSQL advisory lock."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, joinedload

from app.calendar.google_client import (
    GoogleAuthorizationRequired,
    get_authorized_calendar_client,
)
from app.config import Settings
from app.db import get_session_factory
from app.models import (
    AdminSession,
    AdminUser,
    BillingAccount,
    CallSession,
    CallStatus,
    Clinic,
    IntegrationOutbox,
    PaymentRecord,
    PhoneProvisioningOrder,
    PurchaseOrder,
)
from app.call_analysis_service import analyze_call
from app.emailing import email_provider

logger = logging.getLogger(__name__)
_MAINTENANCE_LOCK_ID = 0x4155544F47414C  # "AUTOGAL"
_TERMINAL_STATUSES = (CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.TRANSFERRED)


def _try_lock(session: Session) -> bool:
    return bool(session.scalar(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _MAINTENANCE_LOCK_ID}))


def _unlock(session: Session) -> None:
    session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _MAINTENANCE_LOCK_ID})


def purge_expired_data(session: Session, *, now: datetime | None = None) -> int:
    """Delete terminal calls according to the effective per-clinic retention policy."""
    current = now or datetime.now(UTC)
    delete_ids: list[uuid.UUID] = []
    for clinic in session.scalars(select(Clinic)):
        calls = session.scalars(
            select(CallSession)
            .options(joinedload(CallSession.assistant_config))
            .where(
                CallSession.clinic_id == clinic.id,
                CallSession.status.in_(_TERMINAL_STATUSES),
            )
            .execution_options(yield_per=250)
        )
        for call in calls:
            days = (
                call.assistant_config.conversation_retention_days
                if call.assistant_config is not None
                else clinic.data_retention_days
            )
            if (call.ended_at or call.created_at) < current - timedelta(days=days):
                delete_ids.append(call.id)
            if len(delete_ids) >= 500:
                session.execute(delete(CallSession).where(CallSession.id.in_(delete_ids)))
                delete_ids.clear()
    if delete_ids:
        session.execute(delete(CallSession).where(CallSession.id.in_(delete_ids)))
    result = session.execute(
        delete(AdminSession).where(
            (AdminSession.expires_at <= current) | (AdminSession.revoked_at.is_not(None))
        )
    )
    session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def _mark_outbox_failure(item: IntegrationOutbox, exc: Exception) -> None:
    item.attempts += 1
    item.last_error = str(exc)[:2000]
    item.next_attempt_at = datetime.now(UTC) + timedelta(
        seconds=min(3600, 15 * (2 ** min(item.attempts, 8)))
    )
    if item.attempts >= 12:
        item.status = "dead_letter"




def _resolve_email_payload(session: Session, payload: dict[str, Any]) -> tuple[str, str, str]:
    """Resolve outbox templates without exposing secrets in payloads."""
    if payload.get("to") and payload.get("subject") and payload.get("text"):
        return str(payload["to"]), str(payload["subject"]), str(payload["text"])
    template = str(payload.get("template") or "")
    if template in {"purchase_confirmed", "number_pending"}:
        order = session.get(PurchaseOrder, uuid.UUID(str(payload["order_id"])))
        if order is None:
            raise ValueError("purchase order not found")
        account = session.get(BillingAccount, order.billing_account_id)
        if account is None:
            raise ValueError("billing account not found")
        return (
            account.billing_email,
            "Compra confirmada en Autogal",
            "Hemos confirmado tu compra. Tu número estará activo en menos de 24 horas y te avisaremos por correo electrónico.",
        )
    if template == "number_activated":
        row = session.get(PhoneProvisioningOrder, uuid.UUID(str(payload["provisioning_order_id"])))
        if row is None:
            raise ValueError("provisioning order not found")
        account = session.get(BillingAccount, row.billing_account_id)
        if account is None:
            raise ValueError("billing account not found")
        return account.billing_email, "Tu número Autogal está activo", f"Tu número {row.assigned_number or ''} ya está activo."
    if template in {"invoice_paid", "payment_failed"}:
        payment = session.get(PaymentRecord, uuid.UUID(str(payload["payment_record_id"])))
        if payment is None:
            raise ValueError("payment record not found")
        account = session.get(BillingAccount, payment.billing_account_id)
        if account is None:
            raise ValueError("billing account not found")
        if template == "invoice_paid":
            return account.billing_email, "Factura disponible en Autogal", "Tu pago se ha confirmado y la factura está disponible en tu área de cliente."
        return account.billing_email, "No se pudo completar un pago de Autogal", "No se pudo completar el pago. Revisa el método de pago desde Gestionar suscripción."
    raise ValueError(f"unsupported email template: {template}")

def process_outbox(session: Session, settings: Settings, *, limit: int = 50) -> int:
    """Retry pending integration compensations with exponential backoff."""
    now = datetime.now(UTC)
    items = list(
        session.scalars(
            select(IntegrationOutbox)
            .where(
                IntegrationOutbox.status == "pending",
                IntegrationOutbox.next_attempt_at <= now,
            )
            .order_by(IntegrationOutbox.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    )
    completed = 0
    for item in items:
        payload: dict[str, Any] = item.payload_json
        try:
            if item.kind == "google_calendar.delete_event":
                clinic_id = uuid.UUID(str(payload["clinic_id"]))
                client = get_authorized_calendar_client(session, settings, clinic_id)
                client.events().delete(
                    calendarId=str(payload["calendar_id"]),
                    eventId=str(payload["event_id"]),
                    sendUpdates="none",
                ).execute()
            elif item.kind == "email.send":
                to, subject, body = _resolve_email_payload(session, payload)
                email_provider(settings).send(to=to, subject=subject, text=body)
            elif item.kind == "call_analysis.create":
                if settings.call_analysis_enabled:
                    analyze_call(session, settings, uuid.UUID(str(payload["call_session_id"])))
            else:
                raise ValueError(f"unsupported outbox kind: {item.kind}")
        except (Exception, GoogleAuthorizationRequired) as exc:
            _mark_outbox_failure(item, exc)
            logger.warning(
                "integration_outbox_retry_failed",
                extra={"outbox_id": str(item.id), "kind": item.kind, "attempts": item.attempts},
            )
        else:
            item.status = "completed"
            item.completed_at = datetime.now(UTC)
            item.last_error = None
            completed += 1
    session.commit()
    return completed


def run_maintenance_once(settings: Settings) -> None:
    """Run one exclusive maintenance cycle."""
    with get_session_factory()() as session:
        if not _try_lock(session):
            return
        try:
            deleted_sessions = purge_expired_data(session)
            completed_outbox = process_outbox(session, settings)
            logger.info(
                "maintenance_cycle_completed",
                extra={
                    "expired_admin_sessions_deleted": deleted_sessions,
                    "outbox_completed": completed_outbox,
                },
            )
        finally:
            _unlock(session)
            session.commit()


async def maintenance_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Run maintenance without blocking the FastAPI event loop."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_maintenance_once, settings)
        except Exception:
            logger.exception("maintenance_cycle_failed")
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=float(settings.retention_job_interval_seconds)
            )
        except TimeoutError:
            continue
