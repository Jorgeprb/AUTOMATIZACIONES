from __future__ import annotations

import asyncio

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.server import SipGateway, openai_hosted_sip_target

INVITE = (
    "INVITE sip:bot@sip.autogal.es:6060;transport=udp SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-hosted\r\n"
    "From: <sip:+34600111222@voip.example>;tag=abc\r\n"
    "To: <sip:bot@sip.autogal.es>\r\n"
    "Call-ID: hosted-1\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Length: 0\r\n\r\n"
)


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


class FakeBackend:
    async def resolve_voice_context(self, **kwargs: object) -> VoiceContext:
        return VoiceContext(
            clinic_id="clinic-id",
            call_session_id="call-session-id",
            phone_number_id=None,
            assistant_config_id="config-id",
            model="gpt-realtime-2",
            realtime_voice="marin",
            voice_provider="openai",
            tts_model=None,
            voice_id=None,
            voice_locale="es-ES",
            voice_gender=None,
            azure_speech_region=None,
            voice_style=None,
            voice_speed="1.00",
            voice_pitch="0.00",
            voice_stability=None,
            voice_similarity=None,
            voice_temperature=None,
            output_audio_format="pcm16",
            telephony_codec="pcma",
            preview_audio_format="wav",
            allow_interruptions=True,
            idle_timeout_ms=None,
            transcript_enabled=False,
            first_message="Hola",
            instructions="Instrucciones",
            tools=[],
            call_audio_mode="openai_hosted_sip",
            openai_project_id="proj_test",
        )


def test_openai_hosted_sip_target_uses_project_and_tls() -> None:
    settings = GatewaySettings(openai_api_key="test-key", openai_project_id="proj_123")

    assert (
        openai_hosted_sip_target(settings)
        == "sip:proj_123@sip.api.openai.com;transport=tls"
    )


def test_openai_hosted_sip_is_blocked_clear_without_local_bridge() -> None:
    async def run() -> None:
        settings = GatewaySettings(
            openai_api_key="test-key",
            openai_project_id="proj_test",
            openai_hosted_sip_strategy="blocked",
        )
        gateway = SipGateway(settings)
        transport = FakeTransport()
        gateway.transport = transport  # type: ignore[assignment]
        gateway.backend = FakeBackend()  # type: ignore[assignment]

        await gateway.handle_datagram(INVITE.encode(), ("10.0.0.1", 5060))

        responses = [
            data.decode("utf-8", errors="replace")
            for data, _ in transport.sent
        ]
        assert any(response.startswith("SIP/2.0 100 Trying") for response in responses)
        final = responses[-1]
        assert final.startswith("SIP/2.0 488")
        assert "X-Autogal-Route: openai_hosted_sip_blocked" in final
        assert "sip:proj_test@sip.api.openai.com;transport=tls" in final
        assert gateway.calls_by_id == {}

    asyncio.run(run())
