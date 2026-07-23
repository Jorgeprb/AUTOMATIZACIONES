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
    CallSession,
    CallStatus,
    Clinic,
    IntegrationOutbox,
)

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
            if item.kind != "google_calendar.delete_event":
                raise ValueError(f"unsupported outbox kind: {item.kind}")
            clinic_id = uuid.UUID(str(payload["clinic_id"]))
            client = get_authorized_calendar_client(session, settings, clinic_id)
            client.events().delete(
                calendarId=str(payload["calendar_id"]),
                eventId=str(payload["event_id"]),
                sendUpdates="none",
            ).execute()
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
