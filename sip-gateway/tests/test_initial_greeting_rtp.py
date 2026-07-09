from __future__ import annotations

import asyncio

from sip_gateway.backend import TTSAudio, VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.rtp import RTPPacket, RTPPortPool
from sip_gateway.sdp import SdpOffer
from sip_gateway.session import INITIAL_GREETING, GatewayCallSession
from sip_gateway.sip import SipMessage


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        pass


class FakeBackend:
    def __init__(self) -> None:
        self.tts_texts: list[str] = []

    async def synthesize_tts(self, *, context: VoiceContext, text: str) -> TTSAudio:
        self.tts_texts.append(text)
        return TTSAudio(audio=bytes([0xD5]) * 2400, media_type="audio/pcma")


class FakeBridge:
    first_audio_latency_ms = None

    async def start(self) -> None:
        await asyncio.sleep(10)

    async def close(self) -> None:
        pass


def _context() -> VoiceContext:
    return VoiceContext(
        clinic_id="clinic-id",
        call_session_id="call-session-id",
        phone_number_id=None,
        assistant_config_id="config-id",
        model="gpt-realtime-2",
        realtime_voice="marin",
        voice_provider="azure",
        tts_model="azure-neural",
        voice_id="gl-ES-SabelaNeural",
        voice_locale="gl-ES",
        voice_gender="Female",
        azure_speech_region="westeurope",
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
        transcript_enabled=True,
        first_message="",
        instructions="Instrucións",
        tools=[],
    )


def test_initial_greeting_is_sent_as_rtp_after_ack() -> None:
    async def run() -> None:
        invite = SipMessage.parse(
            b"INVITE sip:bot@sip.autogal.es SIP/2.0\r\n"
            b"Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-test\r\n"
            b"From: <sip:+34600111222@example.com>;tag=abc\r\n"
            b"To: <sip:bot@sip.autogal.es>\r\n"
            b"Call-ID: call-123\r\n"
            b"CSeq: 1 INVITE\r\n"
            b"Content-Length: 0\r\n\r\n"
        )
        fake_backend = FakeBackend()
        call = GatewayCallSession(
            settings=GatewaySettings(
                openai_api_key="test-key",
                telephony_codec="pcma",
                rtp_initial_buffer_ms=200,
                rtp_packet_log_every=1000,
            ),
            backend=fake_backend,  # type: ignore[arg-type]
            port_pool=RTPPortPool(10000, 10000),
            invite=invite,
            sip_addr=("127.0.0.1", 5060),
            offer=SdpOffer("127.0.0.1", 4000, [8]),
            payload_type=8,
            rtp_port=10000,
        )
        call.context = _context()
        call.rtp_transport = FakeTransport()  # type: ignore[assignment]
        call.bridge = FakeBridge()  # type: ignore[assignment]

        call._spawn(call._rtp_sender_loop())
        await call._speak_text(INITIAL_GREETING, reason="initial_greeting")
        await asyncio.sleep(0.08)
        await call.close("test")

        assert fake_backend.tts_texts == [INITIAL_GREETING]
        assert call.rtp_transport.sent  # type: ignore[union-attr]
        packet = RTPPacket.parse(
            call.rtp_transport.sent[0][0]  # type: ignore[union-attr]
        )
        assert packet.payload_type == 8
        assert len(packet.payload) == 160

    asyncio.run(run())
