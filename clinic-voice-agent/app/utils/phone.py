"""Small dependency-free phone normalization helpers.

The project stores caller identifiers in E.164-like form. This helper is deliberately
conservative: it preserves a leading plus, removes formatting, and never invents a
country code. Clinics may later replace it with libphonenumber without changing callers.
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D+")


def normalize_phone(value: str) -> str:
    """Return a stable E.164-like identifier suitable for comparisons."""
    raw = value.strip()
    if not raw:
        return raw
    has_plus = raw.startswith("+")
    digits = _NON_DIGIT.sub("", raw)
    if raw.startswith("00") and len(digits) > 2:
        digits = digits[2:]
        has_plus = True
    if not digits:
        return raw[:32]
    return ("+" if has_plus else "") + digits[:31]
