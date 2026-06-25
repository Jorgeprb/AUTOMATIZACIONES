"""Delete terminal call sessions older than each clinic's retention policy."""

from __future__ import annotations

import argparse
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db import get_session_factory
from app.models import CallSession, CallStatus, Clinic
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)
TERMINAL_CALL_STATUSES = (
    CallStatus.COMPLETED,
    CallStatus.FAILED,
    CallStatus.TRANSFERRED,
)


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """Counts produced by one retention pass."""

    matched: int
    deleted: int


def purge_expired_calls(
    session: Session,
    *,
    now: datetime | None = None,
    clinic_id: uuid.UUID | None = None,
    dry_run: bool = False,
) -> PurgeResult:
    """Apply each clinic's `data_retention_days` to terminal calls."""
    current = now or datetime.now(UTC)
    clinics_query = select(Clinic)
    if clinic_id is not None:
        clinics_query = clinics_query.where(Clinic.id == clinic_id)
    clinics = list(session.scalars(clinics_query))
    matched_ids: list[uuid.UUID] = []
    for clinic in clinics:
        calls = session.scalars(
            select(CallSession)
            .options(joinedload(CallSession.assistant_config))
            .where(
                CallSession.clinic_id == clinic.id,
                CallSession.status.in_(TERMINAL_CALL_STATUSES),
            )
        )
        for call in calls:
            retention_days = (
                call.assistant_config.conversation_retention_days
                if call.assistant_config is not None
                else clinic.data_retention_days
            )
            cutoff = current - timedelta(days=retention_days)
            call_date = call.ended_at or call.created_at
            if call_date < cutoff:
                matched_ids.append(call.id)

    if dry_run or not matched_ids:
        session.rollback()
        return PurgeResult(matched=len(matched_ids), deleted=0)

    session.execute(delete(CallSession).where(CallSession.id.in_(matched_ids)))
    session.commit()
    return PurgeResult(
        matched=len(matched_ids),
        deleted=len(matched_ids),
    )


def _parser() -> argparse.ArgumentParser:
    """Build purge command arguments."""
    parser = argparse.ArgumentParser(
        description="Purga llamadas según la retención de cada clínica.",
    )
    parser.add_argument("--clinic-id", type=uuid.UUID)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one database retention pass."""
    args = _parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    with get_session_factory()() as session:
        result = purge_expired_calls(
            session,
            clinic_id=args.clinic_id,
            dry_run=args.dry_run,
        )
    logger.info(
        "call_retention_purge_completed",
        extra={
            "matched": result.matched,
            "deleted": result.deleted,
            "dry_run": args.dry_run,
            "clinic_id": str(args.clinic_id) if args.clinic_id else None,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
