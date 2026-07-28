"""Natural spoken appointment confirmation tests."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.calendar.spoken_datetime import format_spoken_appointment

MADRID = ZoneInfo("Europe/Madrid")


def test_spanish_confirmation_contains_day_month_and_morning_hour() -> None:
    value = datetime(2026, 8, 26, 12, 0, tzinfo=MADRID)
    assert (
        format_spoken_appointment(value, "es-ES")
        == "el 26 de agosto a las doce de la mañana"
    )


def test_spanish_confirmation_uses_natural_half_hour() -> None:
    value = datetime(2026, 8, 26, 17, 30, tzinfo=MADRID)
    assert (
        format_spoken_appointment(value, "es")
        == "el 26 de agosto a las cinco y media de la tarde"
    )


def test_galician_confirmation_contains_full_natural_datetime() -> None:
    value = datetime(2026, 8, 26, 9, 15, tzinfo=MADRID)
    assert (
        format_spoken_appointment(value, "gl-ES")
        == "o 26 de agosto ás nove e cuarto da mañá"
    )
