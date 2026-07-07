from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

from sip_gateway.backend import TTSAudio, VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import OpenAIRealtimeBridge
from sip_gateway.rtp import RTPPortPool
from sip_gateway.sdp import PAYLOAD_PCMA, parse_sdp_offer
from sip_gateway.session import GatewayCallSession
from sip_gateway.sip import SipMessage


def azure_context() -> VoiceContext:
    return VoiceContext(
        clinic_id="clinic-id",
        call_session_id="call-session-id",
        phone_number_id=None,
        assistant_config_id="config-id",
        model="gpt-realtime-2",
        realtime_voice="marin",
        voice_provider="azure",
        tts_model="azure-neural-tts",
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
        idle_timeout_ms=6000,
        transcript_enabled=True,
        first_message="Ola",
        instructions="Prompt renderizado",
        tools=[],
        call_audio_mode="vps_media_bridge",
    )


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    def __aiter__(self) -> "FakeWebSocket":
        return self

    async def __anext__(self) -> str:
        await asyncio.sleep(3600)
        raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True


def make_bridge(settings: GatewaySettings, ws: FakeWebSocket) -> OpenAIRealtimeBridge:
    return OpenAIRealtimeBridge(
        settings=settings,
        backend=object(),  # type: ignore[arg-type]
        context=azure_context(),
        call_id="call-id",
        tool_executor=lambda _name, _arguments: asyncio.sleep(0, result={}),
        payload_type=PAYLOAD_PCMA,
    )


def test_realtime_connect_does_not_send_openai_beta(monkeypatch) -> None:
    async def run() -> None:
        captured: dict[str, Any] = {}
        ws = FakeWebSocket()

        async def fake_connect(url: str, **kwargs: Any) -> FakeWebSocket:
            captured["url"] = url
            captured["headers"] = kwargs["additional_headers"]
            return ws

        monkeypatch.setattr("sip_gateway.openai_bridge.connect", fake_connect)
        settings = GatewaySettings(
            openai_api_key="test-key",
            openai_realtime_model="gpt-realtime-2",
        )
        bridge = make_bridge(settings, ws)
        await bridge.start()
        await bridge.close()

        assert captured["url"] == (
            "wss://api.openai.com/v1/realtime?model=gpt-realtime-2"
        )
        assert "Authorization" in captured["headers"]
        assert "OpenAI-Beta" not in captured["headers"]

    asyncio.run(run())


def test_session_update_uses_realtime_ga_shape(monkeypatch) -> None:
    async def run() -> None:
        ws = FakeWebSocket()

        async def fake_connect(_url: str, **_kwargs: Any) -> FakeWebSocket:
            return ws

        monkeypatch.setattr("sip_gateway.openai_bridge.connect", fake_connect)
        settings = GatewaySettings(openai_api_key="test-key")
        bridge = make_bridge(settings, ws)
        await bridge.start()
        await bridge.close()

        event = ws.sent[0]
        session = event["session"]
        assert event["type"] == "session.update"
        assert session["type"] == "realtime"
        assert session["output_modalities"] == ["text"]
        assert session["audio"]["input"]["format"] == {"type": "audio/pcma"}
        assert session["audio"]["input"]["turn_detection"]["type"] == "server_vad"
        assert "modalities" not in session
        assert "input_audio_format" not in session
        assert "output_audio_format" not in session
        assert "voice" not in session
        assert "temperature" not in session
        assert "output" not in session["audio"]

    asyncio.run(run())


def test_beta_api_shape_error_is_logged_and_falls_back_to_tts_text() -> None:
    async def run() -> None:
        settings = GatewaySettings(
            openai_api_key="test-key",
            openai_failure_message="Erro técnico temporal.",
        )
        bridge = OpenAIRealtimeBridge(
            settings=settings,
            backend=object(),  # type: ignore[arg-type]
            context=azure_context(),
            call_id="call-id",
            tool_executor=lambda _name, _arguments: asyncio.sleep(0, result={}),
            payload_type=PAYLOAD_PCMA,
        )
        await bridge._handle_event(
            {
                "type": "error",
                "error": {
                    "code": "beta_api_shape_disabled",
                    "message": "invalid_request_error.beta_api_shape_disabled",
                },
            }
        )
        assert await asyncio.wait_for(bridge.text_queue.get(), timeout=0.1) == (
            "Erro técnico temporal."
        )

    asyncio.run(run())


class FakeBackend:
    def __init__(self) -> None:
        self.tts_texts: list[str] = []

    async def execute_tool(self, **_kwargs: Any) -> dict[str, Any]:
        return {}

    async def synthesize_tts(self, *, context: VoiceContext, text: str) -> TTSAudio:
        self.tts_texts.append(text)
        pcm16 = struct.pack("<" + "h" * 160, *([800] * 160))
        return TTSAudio(audio=pcm16, media_type="audio/pcm")


class FakeBridge:
    def __init__(self, **_kwargs: Any) -> None:
        self.text_queue: asyncio.Queue[str] = asyncio.Queue()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.first_audio_latency_ms = None
        self.output_audio_is_telephony = False

    async def start(self) -> None:
        return None

    async def send_audio(self, _audio_payload: bytes) -> None:
        return None

    async def cancel_response(self) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeTransport:
    def __init__(self) -> None:
        self.packets: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.packets.append((data, addr))

    def close(self) -> None:
        self.closed = True


def test_ack_starts_initial_azure_greeting_rtp(monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr("sip_gateway.session.OpenAIRealtimeBridge", FakeBridge)
        invite = SipMessage.parse(
            (
                "INVITE sip:bot@sip.autogal.es:6060 SIP/2.0\r\n"
                "Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-test\r\n"
                "From: <sip:+34600111222@voip>;tag=abc\r\n"
                "To: <sip:bot@sip.autogal.es>\r\n"
                "Call-ID: call-123\r\n"
                "CSeq: 1 INVITE\r\n"
                "Content-Type: application/sdp\r\n"
                "Content-Length: 120\r\n\r\n"
                "v=0\r\n"
                "o=- 1 1 IN IP4 127.0.0.1\r\n"
                "s=-\r\n"
                "c=IN IP4 127.0.0.1\r\n"
                "t=0 0\r\n"
                "m=audio 4000 RTP/AVP 8\r\n"
                "a=rtpmap:8 PCMA/8000\r\n"
            ).encode()
        )
        offer = parse_sdp_offer(invite.body)
        backend = FakeBackend()
        transport = FakeTransport()
        call = GatewayCallSession(
            settings=GatewaySettings(
                openai_api_key="test-key",
                initial_greeting="Ola, son a asistente virtual da clínica. En que podo axudarche?",
            ),
            backend=backend,  # type: ignore[arg-type]
            port_pool=RTPPortPool(10002, 10002),
            invite=invite,
            sip_addr=("127.0.0.1", 5060),
            offer=offer,
            payload_type=PAYLOAD_PCMA,
            rtp_port=10002,
        )
        call.context = azure_context()
        call.rtp_transport = transport  # type: ignore[assignment]

        await call.start_media()
        for _ in range(20):
            if transport.packets:
                break
            await asyncio.sleep(0.02)
        await call.close("test")

        assert backend.tts_texts[0] == (
            "Ola, son a asistente virtual da clínica. En que podo axudarche?"
        )
        assert transport.packets
        assert transport.packets[0][0][1] & 0x7F == PAYLOAD_PCMA

    asyncio.run(run())
