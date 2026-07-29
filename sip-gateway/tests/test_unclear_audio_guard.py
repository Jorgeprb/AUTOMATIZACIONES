from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sip_gateway.backend import VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import (
    OpenAIRealtimeBridge,
    assistant_requested_confirmation,
    build_realtime_session,
    transcript_has_explicit_confirmation,
    transcript_is_clear,
)


def _context(*, transcript_enabled: bool = True) -> VoiceContext:
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
        azure_speech_region="italynorth",
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
        transcript_enabled=transcript_enabled,
        first_message="Ola, en que podo axudarche?",
        instructions="Responde en galego.",
        tools=[],
        language="gl-ES",
        temperature="0.9",
        turn_end_silence_ms=400,
    )


def _bridge(*, transcript_enabled: bool = True) -> OpenAIRealtimeBridge:
    async def executor(name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"ok": True}

    return OpenAIRealtimeBridge(
        settings=GatewaySettings(openai_api_key="test-key"),
        backend=SimpleNamespace(),
        context=_context(transcript_enabled=transcript_enabled),
        call_id="call-1",
        tool_executor=executor,
    )


def test_gpt_realtime_2_session_omits_unsupported_temperature() -> None:
    session = build_realtime_session(_context())
    assert "temperature" not in session
    assert session["reasoning"] == {"effort": "low"}
    assert session["audio"]["input"]["turn_detection"]["create_response"] is False


def test_noise_and_fillers_are_not_considered_clear() -> None:
    for transcript in ("", "...", "mmm", "ruido", "eh eh eh", "[inaudible]"):
        assert transcript_is_clear(transcript) is False
    assert transcript_is_clear("Quería pedir una cita mañana") is True


def test_write_action_requires_explicit_latest_turn_confirmation() -> None:
    assert transcript_has_explicit_confirmation("sí") is True
    assert transcript_has_explicit_confirmation("vale, resérvala") is True
    assert transcript_has_explicit_confirmation("mañana a las cinco") is False
    assert transcript_has_explicit_confirmation("mmm") is False


def test_temperature_unknown_parameter_is_nonfatal_compatibility_error() -> None:
    async def run() -> None:
        bridge = _bridge()
        await bridge._handle_event(
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "code": "unknown_parameter",
                    "message": "Unknown parameter: 'session.temperature'.",
                    "param": "session.temperature",
                },
            }
        )
        assert bridge.text_queue.empty()

    asyncio.run(run())


def test_appointment_tool_is_blocked_when_latest_transcript_is_unclear() -> None:
    bridge = _bridge()
    arguments: dict[str, object] = {}
    blocked = bridge._guard_tool_call("create_appointment", arguments)
    assert blocked is not None
    assert blocked["error"] == "unclear_user_input"
    assert arguments["_server_guard_available"] is True
    assert arguments["_server_input_clear"] is False


def test_privacy_disabled_transcription_does_not_emit_fake_guard_evidence() -> None:
    bridge = _bridge(transcript_enabled=False)
    arguments: dict[str, object] = {}
    blocked = bridge._guard_tool_call("check_availability", arguments)
    assert blocked is None
    assert arguments == {"_server_guard_available": False}


def test_clear_input_does_not_require_a_second_confirmation_prompt() -> None:
    assert (
        assistant_requested_confirmation(
            "Tengo sitio mañana a las cinco. ¿Quieres que la reserve?"
        )
        is True
    )
    bridge = _bridge()
    bridge._last_user_input_clear = True
    arguments: dict[str, object] = {}
    assert bridge._guard_tool_call("create_appointment", arguments) is None
    assert arguments["_server_guard_available"] is True
    assert arguments["_server_input_clear"] is True
    assert "_server_confirmation_prompted" not in arguments
    assert "_server_explicit_confirmation" not in arguments
