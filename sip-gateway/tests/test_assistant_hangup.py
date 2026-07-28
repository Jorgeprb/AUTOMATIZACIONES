from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sip_gateway.config import GatewaySettings
from sip_gateway.server import SipGateway
from sip_gateway.sip import SipMessage

INVITE = (
    "INVITE sip:bot@203.0.113.10 SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 198.51.100.10:5060;branch=z9hG4bK-hangup\r\n"
    "From: <sip:+34600111222@voip.example>;tag=remote-tag\r\n"
    "To: <sip:bot@203.0.113.10>\r\n"
    "Contact: <sip:caller@198.51.100.10:5070;transport=udp>\r\n"
    "Call-ID: assistant-hangup-1\r\n"
    "CSeq: 7 INVITE\r\n"
    "Content-Length: 0\r\n\r\n"
)


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


def test_gateway_sends_in_dialog_bye_before_closing_assistant_call() -> None:
    async def run() -> None:
        settings = GatewaySettings(
            openai_api_key="test-key",
            sip_public_ip="203.0.113.10",
            sip_port=6060,
        )
        gateway = SipGateway(settings)
        transport = FakeTransport()
        gateway.transport = transport  # type: ignore[assignment]
        invite = SipMessage.parse(INVITE.encode())
        call = SimpleNamespace(
            _closed=asyncio.Event(),
            invite=invite,
            local_tag="local-tag",
            dialog_remote_addr=("198.51.100.10", 5070),
            call_id=invite.call_id,
        )
        removals: list[str] = []

        async def remove_call(candidate: object, reason: str) -> None:
            assert candidate is call
            removals.append(reason)

        gateway._remove_call = remove_call  # type: ignore[method-assign]
        await gateway._send_bye_and_close(call, "natural_goodbye")  # type: ignore[arg-type]

        assert removals == ["assistant_natural_goodbye"]
        assert len(transport.sent) == 1
        raw, addr = transport.sent[0]
        message = raw.decode("latin-1")
        assert addr == ("198.51.100.10", 5070)
        assert message.startswith(
            "BYE sip:caller@198.51.100.10:5070;transport=udp SIP/2.0"
        )
        assert "From: <sip:bot@203.0.113.10>;tag=local-tag" in message
        assert "To: <sip:+34600111222@voip.example>;tag=remote-tag" in message
        assert "CSeq: 8 BYE" in message

    asyncio.run(run())
