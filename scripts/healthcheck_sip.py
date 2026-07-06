#!/usr/bin/env python3
"""Send a SIP OPTIONS probe to the gateway and expect a 200 OK response."""

from __future__ import annotations

import os
import socket
import sys
import time
import uuid


def main() -> int:
    host = os.getenv("SIP_HEALTH_HOST", "127.0.0.1")
    port = int(os.getenv("SIP_PORT", os.getenv("SIP_HEALTH_PORT", "6060")))
    timeout = float(os.getenv("SIP_HEALTH_TIMEOUT", "3"))
    call_id = f"health-{uuid.uuid4().hex}"
    branch = f"z9hG4bK-{uuid.uuid4().hex[:12]}"
    message = (
        f"OPTIONS sip:bot@{host}:{port} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP 127.0.0.1:0;branch={branch}\r\n"
        "From: <sip:health@localhost>;tag=health\r\n"
        f"To: <sip:bot@{host}>\r\n"
        f"Call-ID: {call_id}\r\n"
        "CSeq: 1 OPTIONS\r\n"
        "Max-Forwards: 70\r\n"
        "Content-Length: 0\r\n"
        "\r\n"
    ).encode("utf-8")
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(message, (host, port))
        try:
            response, _ = sock.recvfrom(4096)
        except socket.timeout:
            print(f"SIP OPTIONS timeout after {timeout}s", file=sys.stderr)
            return 2
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    text = response.decode("latin-1", errors="replace")
    if "SIP/2.0 200" not in text:
        print(text, file=sys.stderr)
        return 1
    print(f"ok sip_options latency_ms={elapsed_ms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
