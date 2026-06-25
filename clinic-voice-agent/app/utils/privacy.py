"""Privacy boundaries for the MVP's stored free text."""

from __future__ import annotations

import re

MAX_GENERAL_REASON_LENGTH = 300


def normalize_general_reason(value: str | None) -> str | None:
    """Store one short administrative reason, never a long clinical narrative."""
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return None
    if len(normalized) > MAX_GENERAL_REASON_LENGTH:
        raise ValueError(
            "reason must be a short general motive, at most "
            f"{MAX_GENERAL_REASON_LENGTH} characters"
        )
    return normalized
