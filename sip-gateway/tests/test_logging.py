"""Structured SIP logs must redact caller identifiers everywhere."""

from __future__ import annotations

import logging
import sys

from sip_gateway.logging import JsonFormatter


def test_formatter_redacts_phone_in_message_and_exception() -> None:
    try:
        raise RuntimeError("failed caller +34981234567")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        "audit",
        logging.ERROR,
        "",
        0,
        "caller +34981234567",
        (),
        exc_info,
    )
    rendered = JsonFormatter().format(record)

    assert "+34981234567" not in rendered
    assert "***567" in rendered
