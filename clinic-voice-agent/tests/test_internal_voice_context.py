"""Internal VPS media-bridge context endpoint tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.internal_voice import VoiceContextRequest, create_voice_context
from app.config import get_settings
from app.models import AssistantConfig, Clinic, PhoneNumber, PhoneProvider


def _assistant_config(
    clinic: Clinic,
    *,
    call_audio_mode: str = "vps_media_bridge",
) -> AssistantConfig:
    """Create one complete active assistant configuration."""
    return AssistantConfig(
        clinic=clinic,
        name=f"Config {clinic.name}",
        realtime_model="gpt-realtime-clinic",
        realtime_voice="marin",
        call_audio_mode=call_audio_mode,
        voice_provider="azure",
        tts_model="azure-neural-tts",
        voice_id="gl-ES-SabelaNeural",
        voice_locale="gl-ES",
        voice_gender="Female",
        azure_speech_region="westeurope",
        telephony_codec="pcmu",
        output_audio_format="pcm16",
        preview_audio_format="wav",
        language="gl-ES",
        first_message=f"Ola, son o asistente de {clinic.name}.",
        system_prompt="Atiende llamadas de clínica con brevedad.",
        safety_prompt="No des consejo médico.",
        booking_policy_prompt="Confirma antes de reservar.",
        cancellation_policy_prompt="Confirma antes de cancelar.",
        transfer_policy_prompt="Transfiere si lo pide la persona.",
        is_active=True,
    )


def test_context_accepts_sip_metadata_and_returns_sabela_config(
    db_session: Session,
) -> None:
    """A bot route alias must still resolve the clinic from the real DID."""
    clinic = Clinic(
        name="Clínica Sabela",
        timezone="Europe/Madrid",
        phone_number="+34910002000",
        default_language="gl-ES",
        email="info@sabela.test",
    )
    phone = PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number="+34910002000",
        label="VoIP Studio",
    )
    config = _assistant_config(clinic)
    db_session.add_all([clinic, phone, config])
    db_session.commit()

    response = create_voice_context(
        VoiceContextRequest(
            caller="+34600111222",
            caller_phone="+34600111222",
            callee="bot",
            called_number="+34910002000",
            sip_to="<sip:bot@sip.autogal.es:6060>",
            sip_from="<sip:+34600111222@voipstudio.example>;tag=abc",
            openai_call_id="vps-test-call",
            provider_call_id="sip-call-id",
        ),
        db_session,
        get_settings(),
    )

    assert response.clinic_id == clinic.id
    assert response.phone_number_id == phone.id
    assert response.call_audio_mode == "vps_media_bridge"
    assert response.voice_provider == "azure"
    assert response.voice_id == "gl-ES-SabelaNeural"
    assert response.voice_locale == "gl-ES"
    assert response.telephony_codec == "pcmu"
    assert response.prompt == response.instructions
    assert response.called_number == "+34910002000"
    assert response.caller == "+34600111222"
    assert response.clinic.name == "Clínica Sabela"
    assert response.tools


def test_context_uses_single_clinic_fallback_only_when_safe(
    db_session: Session,
) -> None:
    """Fallback without DID is only allowed for a single active configured clinic."""
    clinic = Clinic(
        name="Clínica Única",
        timezone="Europe/Madrid",
        phone_number="+34910003000",
    )
    PhoneNumber(
        clinic=clinic,
        provider=PhoneProvider.VOIPSTUDIO,
        phone_number="+34910003000",
        label="Principal",
    )
    db_session.add_all([clinic, _assistant_config(clinic)])
    db_session.commit()

    response = create_voice_context(
        VoiceContextRequest(
            callee="bot",
            sip_to="<sip:bot@sip.autogal.es:6060>",
            openai_call_id="vps-fallback-call",
            provider_call_id="sip-fallback-id",
        ),
        db_session,
        get_settings(),
    )

    assert response.clinic_id == clinic.id
    assert response.called_number == "+34910003000"


def test_context_rejects_unsafe_fallback_with_multiple_active_clinics(
    db_session: Session,
) -> None:
    """Never guess a tenant when several clinics could receive the alias."""
    first = Clinic(
        name="Clínica A",
        timezone="Europe/Madrid",
        phone_number="+34910004000",
    )
    second = Clinic(
        name="Clínica B",
        timezone="Europe/Madrid",
        phone_number="+34910005000",
    )
    db_session.add_all(
        [first, second, _assistant_config(first), _assistant_config(second)]
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_voice_context(
            VoiceContextRequest(
                callee="bot",
                sip_to="<sip:bot@sip.autogal.es:6060>",
                openai_call_id="vps-unsafe-call",
                provider_call_id="sip-unsafe-id",
            ),
            db_session,
            get_settings(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "clinic_not_found"
