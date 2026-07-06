from __future__ import annotations

import asyncio

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.rtp import RTPPortPool
from sip_gateway.sdp import parse_sdp_offer
from sip_gateway.server import SipGateway
from sip_gateway.session import GatewayCallSession
from sip_gateway.sip import SipMessage

INVITE = (
    "INVITE sip:+34881170837@203.0.113.10 SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-life\r\n"
    "From: <sip:+34600111222@voip.example>;tag=abc\r\n"
    "To: <sip:+34881170837@203.0.113.10>\r\n"
    "Call-ID: lifecycle-1\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Type: application/sdp\r\n"
    "Content-Length: 120\r\n"
    "\r\n"
    "v=0\r\n"
    "o=- 1 1 IN IP4 127.0.0.1\r\n"
    "s=-\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 4000 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
)


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
            telephony_codec="pcmu",
            preview_audio_format="wav",
            allow_interruptions=True,
            idle_timeout_ms=None,
            transcript_enabled=False,
            first_message="Hola",
            instructions="Instrucciones",
            tools=[],
        )


def test_call_prepare_and_cleanup_releases_rtp_port() -> None:
    async def run() -> None:
        settings = GatewaySettings(
            openai_api_key="test-key",
            sip_bind_host="127.0.0.1",
            sip_public_ip="127.0.0.1",
            rtp_port_min=13000,
            rtp_port_max=13000,
        )
        invite = SipMessage.parse(INVITE.encode())
        offer = parse_sdp_offer(invite.body)
        port_pool = RTPPortPool(13000, 13000)
        rtp_port = port_pool.lease()
        call = GatewayCallSession(
            settings=settings,
            backend=FakeBackend(),  # type: ignore[arg-type]
            port_pool=port_pool,
            invite=invite,
            sip_addr=("127.0.0.1", 5060),
            offer=offer,
            payload_type=offer.choose_payload(),
            rtp_port=rtp_port,
        )

        await call.prepare()
        assert call.context is not None
        assert call.rtp_transport is not None
        await call.close("test")
        assert port_pool.lease() == 13000

    asyncio.run(run())


def test_gateway_metrics_snapshot_starts_empty() -> None:
    settings = GatewaySettings(
        openai_api_key="test-key",
        sip_bind_host="127.0.0.1",
        sip_public_ip="127.0.0.1",
        rtp_port_min=13000,
        rtp_port_max=13004,
    )
    gateway = SipGateway(settings)

    snapshot = gateway.metrics_snapshot()

    assert snapshot["ok"] is True
    assert snapshot["active_calls"] == 0
    assert snapshot["rtp_active"] == 0
    assert snapshot["sessions_orphaned"] == 0
    assert snapshot["rtp_ports_available"] == 3
