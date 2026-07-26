from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import (
    OpenAIRealtimeBridge,
    build_realtime_session,
)


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


def test_external_tts_session_uses_text_and_manual_transcript_gating() -> None:
    session = build_realtime_session(_context())
    assert session["output_modalities"] == ["text"]
    assert session["instructions"] == "Responde en español."
    assert session["audio"]["input"]["turn_detection"]["create_response"] is False
    assert "temperature" not in session


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
        assert bridge._response_create_inflight is False

    asyncio.run(run())
