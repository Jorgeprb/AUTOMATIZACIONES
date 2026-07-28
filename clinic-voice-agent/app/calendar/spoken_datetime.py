"""Natural spoken appointment date/time rendering for voice responses."""

from __future__ import annotations

from datetime import datetime

_MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_MONTHS_GL = (
    "xaneiro", "febreiro", "marzo", "abril", "maio", "xuño",
    "xullo", "agosto", "setembro", "outubro", "novembro", "decembro",
)
_HOURS_ES = (
    "doce", "una", "dos", "tres", "cuatro", "cinco", "seis",
    "siete", "ocho", "nueve", "diez", "once",
)
_HOURS_GL = (
    "doce", "unha", "dúas", "tres", "catro", "cinco", "seis",
    "sete", "oito", "nove", "dez", "once",
)


def _period_es(hour: int) -> str:
    if 6 <= hour <= 12:
        return "de la mañana"
    if 13 <= hour < 20:
        return "de la tarde"
    return "de la noche"


def _period_gl(hour: int) -> str:
    if 6 <= hour <= 12:
        return "da mañá"
    if 13 <= hour < 20:
        return "da tarde"
    return "da noite"


def _spoken_clock_es(value: datetime) -> str:
    hour12 = value.hour % 12
    article = "la" if hour12 == 1 else "las"
    base = f"{article} {_HOURS_ES[hour12]}"
    minute = value.minute
    if minute == 0:
        clock = base
    elif minute == 15:
        clock = f"{base} y cuarto"
    elif minute == 30:
        clock = f"{base} y media"
    elif minute == 45:
        next_hour = (hour12 + 1) % 12
        next_article = "la" if next_hour == 1 else "las"
        clock = f"{next_article} {_HOURS_ES[next_hour]} menos cuarto"
    else:
        clock = f"{base} y {minute:02d}"
    return f"{clock} {_period_es(value.hour)}"


def _spoken_clock_gl(value: datetime) -> str:
    hour12 = value.hour % 12
    article = "a" if hour12 == 1 else "as"
    base = f"{article} {_HOURS_GL[hour12]}"
    minute = value.minute
    if minute == 0:
        clock = base
    elif minute == 15:
        clock = f"{base} e cuarto"
    elif minute == 30:
        clock = f"{base} e media"
    elif minute == 45:
        next_hour = (hour12 + 1) % 12
        next_article = "a" if next_hour == 1 else "as"
        clock = f"{next_article} {_HOURS_GL[next_hour]} menos cuarto"
    else:
        clock = f"{base} e {minute:02d}"
    return f"{clock} {_period_gl(value.hour)}"


def format_spoken_appointment(value: datetime, language: str) -> str:
    """Render `26 de agosto a las doce de la mañana` in the call language."""
    code = (language or "es").strip().replace("_", "-").split("-", 1)[0].casefold()
    if code == "gl":
        clock = _spoken_clock_gl(value)
        if clock.startswith("a "):
            spoken_clock = f"á {clock[2:]}"
        else:
            spoken_clock = f"ás {clock.removeprefix('as ')}"
        return f"o {value.day} de {_MONTHS_GL[value.month - 1]} {spoken_clock}"
    return (
        f"el {value.day} de {_MONTHS_ES[value.month - 1]} "
        f"a {_spoken_clock_es(value)}"
    )
