"""Compact structured logging with automatic secret and PII redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, ClassVar

_SECRET_KEYS = ("password", "secret", "token", "authorization", "api_key", "cookie")
_TEXT_KEYS = ("transcript", "instructions", "prompt", "body", "payload")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d .()\-]{7,}\d)(?!\w)")
_SIP_USER_RE = re.compile(r"(sip:)([^@;>\s]+)", flags=re.IGNORECASE)


def _redact(key: str, value: Any) -> Any:
    lowered = key.casefold()
    if any(marker in lowered for marker in _SECRET_KEYS):
        return "[REDACTED]"
    if any(marker in lowered for marker in _TEXT_KEYS) and value not in (None, ""):
        return "[REDACTED_CONTENT]"
    if isinstance(value, str):
        value = _SIP_USER_RE.sub(r"\1***", value)
        return _PHONE_RE.sub(lambda m: f"***{re.sub(r'\\D', '', m.group(1))[-3:]}", value)
    if isinstance(value, dict):
        return {str(k): _redact(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact(key, item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    RESERVED: ClassVar[set[str]] = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact("message", record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = _redact(key, value)
        if record.exc_info:
            payload["exc_info"] = _redact("exception", self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), handlers=[handler], force=True)
