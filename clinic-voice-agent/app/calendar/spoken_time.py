"""Telephone-friendly date and time rendering for assistant tool results."""

from __future__ import annotations

from datetime import datetime

_HOURS_ES = {
    0: "doce",
    1: "una",
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
    11: "once",
    12: "doce",
    13: "una",
    14: "dos",
    15: "tres",
    16: "cuatro",
    17: "cinco",
    18: "seis",
    19: "siete",
    20: "ocho",
    21: "nueve",
    22: "diez",
    23: "once",
}

_MINUTES_ES = {
    1: "uno",
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
    11: "once",
    12: "doce",
    13: "trece",
    14: "catorce",
    16: "dieciséis",
    17: "diecisiete",
    18: "dieciocho",
    19: "diecinueve",
    20: "veinte",
    21: "veintiuno",
    22: "veintidós",
    23: "veintitrés",
    24: "veinticuatro",
    25: "veinticinco",
    26: "veintiséis",
    27: "veintisiete",
    28: "veintiocho",
    29: "veintinueve",
}


def _article(hour: int) -> str:
    return "la" if hour % 12 == 1 else "las"


def _minute_words(value: int) -> str:
    if value in _MINUTES_ES:
        return _MINUTES_ES[value]
    if 30 < value < 40:
        return f"treinta y {_MINUTES_ES[value - 30]}"
    return str(value)


def format_spoken_time(value: datetime, style: str = "natural_quarters") -> str:
    """Return a deterministic Spanish rendering suitable for TTS."""
    hour = value.hour
    minute = value.minute
    if style == "numeric":
        return f"{value:%H:%M}"

    hour_word = _HOURS_ES[hour]
    prefix = f"{_article(hour)} {hour_word}"
    if minute == 0:
        return f"{prefix} en punto"
    if minute == 15:
        return f"{prefix} y cuarto"
    if minute == 30:
        return f"{prefix} y media"
    next_hour = (hour + 1) % 24
    if minute == 45:
        return f"{_article(next_hour)} {_HOURS_ES[next_hour]} menos cuarto"
    if minute > 30:
        remaining = 60 - minute
        return (
            f"{_article(next_hour)} {_HOURS_ES[next_hour]} "
            f"menos {_minute_words(remaining)}"
        )
    return f"{prefix} y {_minute_words(minute)}"
