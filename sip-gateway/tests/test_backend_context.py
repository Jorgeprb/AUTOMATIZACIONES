"""Backend contract helpers for the SIP gateway."""

from __future__ import annotations

from sip_gateway.backend import BackendClient, VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.session import select_called_number
from sip_gateway.sip import SipMessage


def test_select_called_number_prefers_fallback_for_bot_alias() -> None:
    invite = SipMessage.parse(
        b"INVITE sip:bot@sip.autogal.es:6060 SIP/2.0\r\n"
        b"Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-test\r\n"
        b"From: <sip:+34600111222@voipstudio.example>;tag=abc\r\n"
        b"To: <sip:bot@sip.autogal.es>\r\n"
        b"Call-ID: call-123\r\n"
        b"CSeq: 1 INVITE\r\n"
        b"Content-Length: 0\r\n\r\n"
    )

    assert invite.callee == "bot"
    assert select_called_number(invite, "+34910002000") == "+34910002000"


def test_context_payload_includes_sip_headers_and_alias() -> None:
    client = BackendClient(
        GatewaySettings(
            backend_internal_url="http://api:10000",
            openai_api_key="test-openai-key",
            internal_api_key="test-internal-key",
        )
    )

    payload = client._build_context_payload(
        called_number="+34910002000",
        caller_phone="+34600111222",
        caller="+34600111222",
        callee="bot",
        sip_to="<sip:bot@sip.autogal.es>",
        sip_from="<sip:+34600111222@voipstudio.example>;tag=abc",
        openai_call_id="vps-call",
        provider_call_id="sip-call",
    )

    assert payload["called_number"] == "+34910002000"
    assert payload["caller"] == "+34600111222"
    assert payload["callee"] == "bot"
    assert payload["sip_to"] == "<sip:bot@sip.autogal.es>"
    assert payload["sip_from"].startswith("<sip:+34600111222")


def test_voice_context_ignores_future_backend_fields() -> None:
    data = {
        "clinic_id": "clinic-id",
        "call_session_id": "session-id",
        "phone_number_id": "phone-id",
        "assistant_config_id": "config-id",
        "model": "gpt-realtime-clinic",
        "realtime_voice": "marin",
        "voice_provider": "azure",
        "tts_model": "azure-neural-tts",
        "voice_id": "gl-ES-SabelaNeural",
        "voice_locale": "gl-ES",
        "voice_gender": "Female",
        "azure_speech_region": "westeurope",
        "voice_style": None,
        "voice_speed": "1.00",
        "voice_pitch": "0.00",
        "voice_stability": None,
        "voice_similarity": None,
        "voice_temperature": None,
        "output_audio_format": "pcm16",
        "telephony_codec": "pcmu",
        "preview_audio_format": "wav",
        "allow_interruptions": True,
        "idle_timeout_ms": None,
        "transcript_enabled": True,
        "first_message": "Ola",
        "instructions": "Prompt renderizado",
        "tools": [],
        "call_audio_mode": "vps_media_bridge",
        "prompt": "Prompt renderizado",
        "clinic": {"name": "Clínica Sabela"},
        "extra_future_field": "ignored",
    }

    context = VoiceContext.from_response(data)

    assert context.voice_provider == "azure"
    assert context.voice_id == "gl-ES-SabelaNeural"
    assert context.call_audio_mode == "vps_media_bridge"
    assert context.prompt == "Prompt renderizado"
