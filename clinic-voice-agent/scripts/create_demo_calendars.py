"""Create or link the demo calendars "Clínica - Ana" and "Clínica - Luis"."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.calendar.google_client import (
    create_calendar_for_worker,
    get_authorized_calendar_client,
    list_available_calendars,
)
from app.config import get_settings
from app.db import get_session_factory
from app.models import Clinic, Worker
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Ensure exact demo calendar names exist for Ana and Luis."""
    settings = get_settings()
    configure_logging(settings.log_level)

    with get_session_factory()() as session:
        clinic = session.scalar(
            select(Clinic).where(Clinic.phone_number == settings.clinic_phone_number)
        )
        if clinic is None:
            raise RuntimeError("Run `make seed` before creating demo calendars.")

        client = get_authorized_calendar_client(
            session,
            settings,
            clinic.id,
        )
        calendars_by_summary = {
            calendar.summary: calendar for calendar in list_available_calendars(client)
        }
        workers = session.scalars(
            select(Worker).where(
                Worker.clinic_id == clinic.id,
                Worker.name.in_(("Ana", "Luis")),
            )
        ).all()

        for worker in workers:
            summary = f"Clínica - {worker.name}"
            existing = calendars_by_summary.get(summary)
            if existing is not None:
                worker.calendar_id = existing.id
                session.commit()
                calendar_id = existing.id
            else:
                created = create_calendar_for_worker(
                    session,
                    client,
                    worker,
                    summary=summary,
                    color_id=worker.color_id,
                )
                calendars_by_summary[summary] = created
                calendar_id = created.id

            logger.info(
                "demo_worker_calendar_ready",
                extra={
                    "worker_id": str(worker.id),
                    "worker_name": worker.name,
                    "calendar_id": calendar_id,
                    "calendar_summary": summary,
                },
            )


if __name__ == "__main__":
    main()
