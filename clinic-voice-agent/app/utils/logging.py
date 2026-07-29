"""Structured JSON logging with automatic secret and PII redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

_STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
}
_SECRET_KEYS = ("password", "secret", "token", "authorization", "api_key", "cookie")
_TEXT_KEYS = ("transcript", "instructions", "prompt", "body", "payload")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d .()\-]{7,}\d)(?!\w)")
_SIP_USER_RE = re.compile(r"(sip:)([^@;>\s]+)", flags=re.IGNORECASE)
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_QUERY_SECRET_RE = re.compile(
    r"([?&](?:code|state|token|signature|key|secret|authorization)=)[^&#\s]+",
    flags=re.IGNORECASE,
)


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(1))
    return f"***{digits[-3:]}" if digits else "***"


def redact_text(value: str) -> str:
    """Remove phone numbers and SIP users from a log-safe string."""
    value = _SIP_USER_RE.sub(r"\1***", value)
    value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", value)
    return _PHONE_RE.sub(_mask_phone, value)


def redact_value(key: str, value: Any) -> Any:
    """Recursively redact secrets, long free text, and direct identifiers."""
    lowered = key.casefold()
    if any(marker in lowered for marker in _SECRET_KEYS):
        return "[REDACTED]"
    if any(marker in lowered for marker in _TEXT_KEYS) and value not in (None, ""):
        if isinstance(value, (dict, list)):
            return "[REDACTED_STRUCTURED_CONTENT]"
        return "[REDACTED_TEXT]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): redact_value(str(item_key), item)
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_value(key, item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Format log records as one redacted JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_text(record.getMessage()),
        }
        payload.update(
            {
                key: redact_value(key, value)
                for key, value in record.__dict__.items()
                if key not in _STANDARD_LOG_RECORD_FIELDS and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = True
