"""Deterministic telephone-friendly time presentation tests."""

from __future__ import annotations

from datetime import datetime

from app.calendar.spoken_time import format_spoken_time


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 26, hour, minute)


def test_natural_quarter_hours() -> None:
    assert format_spoken_time(_at(17, 0)) == "las cinco en punto"
    assert format_spoken_time(_at(17, 15)) == "las cinco y cuarto"
    assert format_spoken_time(_at(17, 30)) == "las cinco y media"
    assert format_spoken_time(_at(17, 45)) == "las seis menos cuarto"


def test_natural_non_quarter_minutes() -> None:
    assert format_spoken_time(_at(13, 5)) == "la una y cinco"
    assert format_spoken_time(_at(17, 50)) == "las seis menos diez"


def test_numeric_style_preserves_24_hour_value() -> None:
    assert format_spoken_time(_at(17, 15), "numeric") == "17:15"
