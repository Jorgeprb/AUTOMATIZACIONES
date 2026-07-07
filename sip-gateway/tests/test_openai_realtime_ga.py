from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import OpenAIRealtimeBridge, _sanitize_tool_schema


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
        await bridge._handle_event(  # noqa: SLF001
            {
                "type": "error",
                "error": {
                    "code": "invalid_request_error.beta_api_shape_disabled",
                    "message": "beta_api_shape_disabled",
                },
            }
        )
        assert await asyncio.wait_for(bridge.text_queue.get(), timeout=0.1) == "__OPENAI_ERROR__"

    asyncio.run(run())


def test_session_update_shape_has_ga_audio_and_no_beta_fields() -> None:
    external_tts = True
    session: dict[str, Any] = {
        "type": "realtime",
        "instructions": "Instrucións",
        "output_modalities": ["text"] if external_tts else ["text", "audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 8000},
                "turn_detection": {"type": "server_vad", "create_response": True},
            }
        },
    }
    payload = {"type": "session.update", "session": session}
    encoded = json.dumps(payload)

    assert "OpenAI-Beta" not in encoded
    assert session["type"] == "realtime"
    assert "audio" in session
    assert "input" in session["audio"]
    assert "modalities" not in session
    assert "input_audio_format" not in session
    assert "output_audio_format" not in session
    assert "voice" not in session
