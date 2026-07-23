from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import (
    OpenAIRealtimeBridge,
    build_external_greeting_item,
    build_realtime_session,
)
from sip_gateway.rtp import RTPPortPool
from sip_gateway.sdp import parse_sdp_offer
from sip_gateway.session import GatewayCallSession
from sip_gateway.sip import SipMessage


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
        first_message="Hola, soy la asistente virtual. ¿En qué puedo ayudarte?",
        instructions="Responde en español.",
        tools=[],
        language="es",
    )


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


async def _tool_executor(name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"ok": True, "name": name, "arguments": arguments}


def test_external_greeting_is_added_as_assistant_history() -> None:
    event = build_external_greeting_item(_context())
    assert event is not None
    assert event["type"] == "conversation.item.create"
    item = event["item"]
    assert item["role"] == "assistant"
    assert item["content"][0]["type"] == "output_text"
    assert item["content"][0]["text"].startswith("Hola")


def test_session_instructions_mark_greeting_as_already_played_and_keep_language() -> None:
    session = build_realtime_session(_context())
    instructions = session["instructions"]
    assert "ya fue reproducido" in instructions
    assert "No lo repitas" in instructions
    assert "mismo idioma del saludo inicial" in instructions
    assert "idioma configurado `es`" in instructions
    assert "prevalece el idioma del saludo" in instructions
    assert "locale de la voz TTS no" in instructions


def test_duplicate_tool_events_execute_once_and_continue_after_response_done() -> None:
    async def run() -> None:
        calls: list[str] = []

        async def executor(name: str, arguments: dict[str, object]) -> dict[str, object]:
            calls.append(name)
            return {"ok": True}

        websocket = FakeWebSocket()
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=executor,
        )
        bridge._ws = websocket
        bridge._response_active = True
        item = {
            "type": "function_call",
            "name": "get_clinic_info",
            "call_id": "tool-call-1",
            "arguments": "{}",
        }

        await bridge._handle_event({"type": "response.output_item.done", "item": item})
        await bridge._handle_event(
            {
                "type": "response.function_call_arguments.done",
                "name": "get_clinic_info",
                "call_id": "tool-call-1",
                "arguments": "{}",
            }
        )

        assert calls == ["get_clinic_info"]
        assert [m["type"] for m in websocket.messages] == ["conversation.item.create"]

        await bridge._handle_event({"type": "response.done", "response": {}})
        assert [m["type"] for m in websocket.messages] == [
            "conversation.item.create",
            "response.create",
        ]

    asyncio.run(run())


def test_active_response_conflict_is_nonfatal() -> None:
    async def run() -> None:
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=_tool_executor,
        )
        await bridge._handle_event(
            {
                "type": "error",
                "error": {
                    "code": "conversation_already_has_active_response",
                    "message": "Conversation already has an active response",
                },
            }
        )
        assert bridge.text_queue.empty()
        assert bridge._continuation_after_tools is True

    asyncio.run(run())


INVITE = (
    "INVITE sip:+34881170837@203.0.113.10 SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-stability\r\n"
    "From: <sip:+34600111222@voip.example>;tag=abc\r\n"
    "To: <sip:+34881170837@203.0.113.10>\r\n"
    "Call-ID: stability-1\r\n"
    "CSeq: 1 INVITE\r\n"
    "Content-Type: application/sdp\r\n"
    "Content-Length: 120\r\n"
    "\r\n"
    "v=0\r\n"
    "o=- 1 1 IN IP4 127.0.0.1\r\n"
    "s=-\r\n"
    "c=IN IP4 127.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 4000 RTP/AVP 8\r\n"
    "a=rtpmap:8 PCMA/8000\r\n"
)


def test_external_tts_half_duplex_suppresses_echo_during_playout() -> None:
    settings = GatewaySettings(
        openai_api_key="test-key",
        external_tts_half_duplex=True,
        rtp_port_min=14000,
        rtp_port_max=14000,
    )
    invite = SipMessage.parse(INVITE.encode())
    offer = parse_sdp_offer(invite.body)
    call = GatewayCallSession(
        settings=settings,
        backend=SimpleNamespace(),
        port_pool=RTPPortPool(14000, 14000),
        invite=invite,
        sip_addr=("127.0.0.1", 5060),
        offer=offer,
        payload_type=8,
        rtp_port=14000,
    )
    call.context = _context()
    call._bot_speaking = True
    assert call._should_suppress_openai_input(0.0) is True

    call._bot_speaking = False
    call._input_suppressed_until = 10.0
    assert call._should_suppress_openai_input(5.0) is True
    assert call._should_suppress_openai_input(11.0) is False
