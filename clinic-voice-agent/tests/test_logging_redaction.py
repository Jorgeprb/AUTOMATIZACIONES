"""Sensitive identifiers must not escape through structured logging."""

from __future__ import annotations

import json
import logging

from app.utils.logging import JsonFormatter


def test_json_formatter_redacts_email_in_fields_and_messages() -> None:
    record = logging.LogRecord(
        "audit",
        logging.INFO,
        "",
        0,
        "GET /callback?state=fake-state&code=fake-code&email=audit-user@example.test",
        (),
        None,
    )
    record.account_email = "audit-user@example.test"

    payload = json.loads(JsonFormatter().format(record))

    rendered = json.dumps(payload)
    assert "audit-user@example.test" not in rendered
    assert "fake-state" not in rendered
    assert "fake-code" not in rendered
    assert payload["account_email"] == "[REDACTED_EMAIL]"
