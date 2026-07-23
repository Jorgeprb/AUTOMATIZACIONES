from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import (
    OpenAIRealtimeBridge,
    _sanitize_tool_schema,
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
        first_message="Ola",
        instructions="Instrucións",
        tools=[],
    )


def test_realtime_tool_schema_strips_root_oneof() -> None:
    tool = {
        "type": "function",
        "name": "propose_slots",
        "parameters": {
            "type": "object",
            "properties": {},
            "oneOf": [{"required": ["service_id"]}],
        },
    }
    sanitized = _sanitize_tool_schema(tool)
    assert sanitized["parameters"]["type"] == "object"
    assert "oneOf" not in sanitized["parameters"]


def test_openai_error_event_is_queued_not_silent() -> None:
    async def run() -> None:
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=lambda name, arguments: {},  # type: ignore[arg-type]
        )
        await bridge._handle_event(
            {
                "type": "error",
                "error": {
                    "code": "invalid_request_error.beta_api_shape_disabled",
                    "message": "beta_api_shape_disabled",
                },
            }
        )
        assert (
            await asyncio.wait_for(bridge.text_queue.get(), timeout=0.1)
            == "__OPENAI_ERROR__"
        )

    asyncio.run(run())


def test_openai_8000_rate_error_is_suppressed() -> None:
    async def run() -> None:
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=lambda name, arguments: {},  # type: ignore[arg-type]
        )
        await bridge._handle_event(
            {
                "type": "error",
                "error": {
                    "message": (
                        "Invalid session.audio.input.format.rate: got 8000, "
                        "expected >= 24000"
                    ),
                },
            }
        )
        assert (
            await asyncio.wait_for(bridge.text_queue.get(), timeout=0.1)
            == "__OPENAI_CONFIG_ERROR_SUPPRESSED__"
        )

    asyncio.run(run())


def test_session_update_shape_uses_native_g711_and_no_beta_fields() -> None:
    session = build_realtime_session(_context())
    payload = {"type": "session.update", "session": session}
    encoded = json.dumps(payload)

    assert "OpenAI-Beta" not in encoded
    assert "8000" not in encoded
    assert session["type"] == "realtime"
    assert "audio" in session
    assert "input" in session["audio"]
    assert session["audio"]["input"]["format"] == {"type": "audio/pcma"}
    assert session["audio"]["input"]["turn_detection"]["silence_duration_ms"] == 300
    assert session["audio"]["input"]["turn_detection"]["prefix_padding_ms"] == 200
    assert session["reasoning"]["effort"] == "low"
    assert session["output_modalities"] == ["text"]
    assert "modalities" not in session
    assert "input_audio_format" not in session
    assert "output_audio_format" not in session
    assert "output" not in session["audio"]


def test_send_g711_batches_native_telephony_audio_every_40ms() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, str]] = []

        async def send(self, raw: str) -> None:
            self.messages.append(json.loads(raw))

    async def run() -> None:
        websocket = FakeWebSocket()
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=lambda name, arguments: {},  # type: ignore[arg-type]
        )
        bridge._ws = websocket
        await bridge.send_g711(b"\xd5" * 160)
        assert websocket.messages == []
        await bridge.send_g711(b"\xd5" * 160)
        assert len(websocket.messages) == 1
        audio = base64.b64decode(websocket.messages[0]["audio"])
        assert audio == b"\xd5" * 320

    asyncio.run(run())


def test_send_pcm16_resamples_8k_to_24k_before_openai() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, str]] = []

        async def send(self, raw: str) -> None:
            self.messages.append(json.loads(raw))

    async def run() -> None:
        websocket = FakeWebSocket()
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=lambda name, arguments: {},  # type: ignore[arg-type]
        )
        bridge._ws = websocket
        for _ in range(5):
            await bridge.send_pcm16(b"\x00\x00" * 160)

        # 40 ms batches reduce VAD/input latency: five 20 ms frames produce
        # two full batches and keep only the final frame buffered.
        assert len(websocket.messages) == 2
        assert all(
            message["type"] == "input_audio_buffer.append"
            for message in websocket.messages
        )
        audio = base64.b64decode(websocket.messages[0]["audio"])
        assert len(audio) > 320
        assert len(audio) % 2 == 0

    asyncio.run(run())


def test_cancel_not_active_error_is_nonfatal() -> None:
    async def run() -> None:
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=lambda name, arguments: {},  # type: ignore[arg-type]
        )
        await bridge._handle_event(
            {
                "type": "error",
                "error": {
                    "code": "response_cancel_not_active",
                    "message": "Cancellation failed: no active response found",
                },
            }
        )
        assert bridge.text_queue.empty()

    asyncio.run(run())


def test_cancel_response_is_not_sent_when_no_response_is_active() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[str] = []

        async def send(self, raw: str) -> None:
            self.messages.append(raw)

    async def run() -> None:
        websocket = FakeWebSocket()
        bridge = OpenAIRealtimeBridge(
            settings=GatewaySettings(openai_api_key="test-key"),
            backend=SimpleNamespace(),
            context=_context(),
            call_id="call-1",
            tool_executor=lambda name, arguments: {},  # type: ignore[arg-type]
        )
        bridge._ws = websocket
        assert await bridge.cancel_response() is False
        assert websocket.messages == []

    asyncio.run(run())
