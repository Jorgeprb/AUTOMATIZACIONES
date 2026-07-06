"""HTTP client for the FastAPI backend internal voice endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from sip_gateway.config import GatewaySettings


@dataclass(frozen=True, slots=True)
class VoiceContext:
    """Assistant context resolved by backend."""

    clinic_id: str
    call_session_id: str
    phone_number_id: str | None
    assistant_config_id: str
    model: str
    realtime_voice: str
    voice_provider: str
    tts_model: str | None
    voice_id: str | None
    voice_locale: str | None
    voice_gender: str | None
    voice_speed: str
    voice_pitch: str
    voice_stability: str | None
    voice_similarity: str | None
    voice_temperature: str | None
    output_audio_format: str
    telephony_codec: str
    preview_audio_format: str
    allow_interruptions: bool
    idle_timeout_ms: int | None
    transcript_enabled: bool
    first_message: str
    instructions: str
    tools: list[dict[str, Any]]


class BackendClient:
    """Small async client to keep gateway decoupled from FastAPI internals."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._settings.internal_api_key is not None:
            headers["X-Internal-API-Key"] = (
                self._settings.internal_api_key.get_secret_value()
            )
        return headers

    async def resolve_voice_context(
        self,
        *,
        called_number: str,
        caller_phone: str,
        openai_call_id: str,
        provider_call_id: str,
    ) -> VoiceContext:
        """Resolve called DID to clinic prompt/config through backend."""
        payload = {
            "called_number": called_number,
            "caller_phone": caller_phone,
            "openai_call_id": openai_call_id,
            "provider_call_id": provider_call_id,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self._settings.backend_internal_url}/api/internal/voice/context",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
        return VoiceContext(**data)

    async def synthesize_tts(
        self,
        *,
        context: VoiceContext,
        text: str,
    ) -> bytes:
        """Generate one TTS chunk through backend provider layer."""
        payload = {
            "clinic_id": context.clinic_id,
            "text": text,
            "voice_provider": context.voice_provider,
            "realtime_voice": context.realtime_voice,
            "tts_model": context.tts_model,
            "voice_id": context.voice_id,
            "voice_locale": context.voice_locale,
            "voice_gender": context.voice_gender,
            "voice_speed": context.voice_speed,
            "voice_pitch": context.voice_pitch,
            "voice_stability": context.voice_stability,
            "voice_similarity": context.voice_similarity,
            "voice_temperature": context.voice_temperature,
            "output_audio_format": "pcm16",
            "telephony_codec": context.telephony_codec,
            "preview_audio_format": "wav",
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{self._settings.backend_internal_url}/api/internal/voice/tts",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.content

    async def execute_tool(
        self,
        *,
        clinic_id: str,
        call_session_id: str | None,
        openai_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a model tool via backend production dispatcher."""
        payload = {
            "clinic_id": clinic_id,
            "call_session_id": call_session_id,
            "openai_call_id": openai_call_id,
            "name": name,
            "arguments": arguments,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._settings.backend_internal_url}/api/internal/voice/tool",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()
