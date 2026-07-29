"""Reliable email delivery abstraction used by IntegrationOutbox."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, text: str) -> None: ...


@dataclass(slots=True)
class SMTPEmailProvider:
    settings: Settings

    def send(self, *, to: str, subject: str, text: str) -> None:
        if not self.settings.smtp_host or not self.settings.smtp_from_email:
            raise RuntimeError("SMTP is not configured.")
        message = EmailMessage()
        message["From"] = (
            f"{self.settings.smtp_from_name} <{self.settings.smtp_from_email}>"
        )
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=20,
        ) as client:
            if self.settings.smtp_use_tls:
                client.starttls()
            if self.settings.smtp_username:
                client.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password.get_secret_value(),
                )
            client.send_message(message)


def email_provider(settings: Settings) -> EmailProvider:
    return SMTPEmailProvider(settings)
