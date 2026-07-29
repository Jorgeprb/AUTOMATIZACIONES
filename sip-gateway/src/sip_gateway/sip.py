"""Minimal SIP parser and response builder for UDP server mode."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Self

CRLF = "\r\n"
MAX_HEADER_VALUE = 2048
TOKEN_RE = re.compile(r"^[A-Z]+$")


def sanitize_header(value: str | None) -> str:
    """Remove control characters and cap size before logging or echoing."""
    if not value:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return cleaned[:MAX_HEADER_VALUE]


@dataclass(slots=True)
class SipMessage:
    """Parsed SIP message with case-insensitive header lookup."""

    start_line: str
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: str = ""

    @classmethod
    def parse(cls, data: bytes) -> Self:
        """Parse one UDP SIP datagram."""
        text = data.decode("utf-8", errors="replace")
        head, separator, body = text.partition("\r\n\r\n")
        if not separator:
            head, separator, body = text.partition("\n\n")
        lines = [line.rstrip("\r") for line in head.splitlines() if line.strip()]
        if not lines:
            raise ValueError("empty SIP datagram")
        headers: dict[str, list[str]] = {}
        current_name: str | None = None
        for raw_line in lines[1:]:
            if raw_line.startswith((" ", "\t")) and current_name:
                headers[current_name][-1] += " " + sanitize_header(raw_line.strip())
                continue
            name, colon, value = raw_line.partition(":")
            if not colon:
                continue
            key = name.strip().lower()
            current_name = key
            headers.setdefault(key, []).append(sanitize_header(value.strip()))
        content_length = cls(
            start_line=sanitize_header(lines[0]),
            headers=headers,
            body=body,
        ).header_int("content-length")
        if content_length is not None:
            body = body[:content_length]
        return cls(start_line=sanitize_header(lines[0]), headers=headers, body=body)

    @property
    def is_request(self) -> bool:
        """Return whether this is a SIP request."""
        return not self.start_line.upper().startswith("SIP/2.0")

    @property
    def method(self) -> str:
        """Return request method or empty for responses."""
        if not self.is_request:
            return ""
        method = self.start_line.split(" ", maxsplit=1)[0].upper()
        return method if TOKEN_RE.match(method) else ""

    @property
    def request_uri(self) -> str:
        """Return request URI."""
        parts = self.start_line.split()
        return parts[1] if len(parts) >= 2 else ""

    def header(self, name: str, default: str = "") -> str:
        """Return first header value."""
        values = self.headers.get(name.lower())
        return values[0] if values else default

    def header_all(self, name: str) -> list[str]:
        """Return all values for a header."""
        return list(self.headers.get(name.lower(), []))

    def header_int(self, name: str) -> int | None:
        """Return integer header value when present and valid."""
        value = self.header(name)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def call_id(self) -> str:
        """Return sanitized Call-ID."""
        return self.header("call-id") or self.header("i")

    @property
    def cseq(self) -> str:
        """Return sanitized CSeq."""
        return self.header("cseq")

    @property
    def branch(self) -> str:
        """Return first Via branch parameter if present."""
        via = self.header("via") or self.header("v")
        match = re.search(r"(?:^|;)branch=([^;\s]+)", via, flags=re.IGNORECASE)
        return sanitize_header(match.group(1) if match else "")

    @property
    def from_tag(self) -> str:
        """Return From tag if present."""
        return _tag_from_header(self.header("from") or self.header("f"))

    @property
    def to_tag(self) -> str:
        """Return To tag if present."""
        return _tag_from_header(self.header("to") or self.header("t"))

    @property
    def caller(self) -> str:
        """Return caller URI/user from From header."""
        return extract_sip_user(self.header("from") or self.header("f"))

    @property
    def callee(self) -> str:
        """Return called URI/user from To header or request URI."""
        return extract_sip_user(
            self.header("to") or self.header("t")
        ) or extract_sip_user(self.request_uri)


def _tag_from_header(value: str) -> str:
    match = re.search(r"(?:^|;)tag=([^;\s>]+)", value, flags=re.IGNORECASE)
    return sanitize_header(match.group(1) if match else "")


def extract_sip_user(value: str) -> str:
    """Extract user part from SIP URI-ish values."""
    sanitized = sanitize_header(value)
    uri_match = re.search(r"sip:([^@;>\s]+)", sanitized, flags=re.IGNORECASE)
    if uri_match:
        return uri_match.group(1)
    number_match = re.search(r"\+?\d{5,}", sanitized)
    return number_match.group(0) if number_match else ""


def build_response(
    request: SipMessage,
    status_code: int,
    reason: str,
    *,
    body: str = "",
    contact: str | None = None,
    to_tag: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    """Build a minimal SIP response preserving transaction headers."""
    headers: list[tuple[str, str]] = []
    for via in request.header_all("via") or request.header_all("v"):
        headers.append(("Via", via))
    from_value = request.header("from") or request.header("f")
    to_value = request.header("to") or request.header("t")
    if to_tag and "tag=" not in to_value.lower():
        separator = ";" if to_value else ""
        to_value = f"{to_value}{separator}tag={to_tag}"
    headers.extend(
        [
            ("From", from_value),
            ("To", to_value),
            ("Call-ID", request.call_id),
            ("CSeq", request.cseq),
        ]
    )
    if contact:
        headers.append(("Contact", contact))
    if extra_headers:
        headers.extend((name, value) for name, value in extra_headers.items())
    content_type = "application/sdp" if body else "text/plain"
    headers.extend(
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body.encode("utf-8")))),
        ]
    )
    head = [f"SIP/2.0 {status_code} {reason}"]
    head.extend(f"{name}: {sanitize_header(value)}" for name, value in headers)
    return (CRLF.join(head) + CRLF * 2 + body).encode("utf-8")


def build_request(
    method: str,
    uri: str,
    headers: dict[str, str],
    body: str = "",
) -> bytes:
    """Build a simple SIP request for tests/future outbound use."""
    lines = [f"{method} {uri} SIP/2.0"]
    for name, value in headers.items():
        lines.append(f"{name}: {sanitize_header(value)}")
    lines.append(f"Content-Length: {len(body.encode('utf-8'))}")
    return (CRLF.join(lines) + CRLF * 2 + body).encode("utf-8")
