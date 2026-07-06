"""OpenAI TTS and voice catalog provider."""

from __future__ import annotations

import httpx

from app.config import Settings
from app.voice_providers.base import (
    TTSRequest,
    TTSResult,
    VoiceCatalogItem,
    VoiceProviderCredentialError,
    VoiceProviderError,
    VoiceProviderInfo,
)

OPENAI_REALTIME_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
)
OPENAI_TTS_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
)


class OpenAITTSProvider:
    """Finite OpenAI speech provider."""

    provider_id = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def info(self) -> VoiceProviderInfo:
        """Return provider metadata without exposing secrets."""
        configured = bool(self._settings.openai_api_key.get_secret_value().strip())
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="OpenAI",
            configured=configured,
            supports_streaming=True,
            recommended=True,
            notes="Compatible con OpenAI Hosted SIP y VPS Media Bridge.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return locally configured OpenAI Realtime and TTS voices."""
        models = list(dict.fromkeys([self._settings.openai_tts_model]))
        items: list[VoiceCatalogItem] = []
        for voice in OPENAI_TTS_VOICES:
            for model in models:
                items.append(
                    VoiceCatalogItem(
                        provider=self.provider_id,
                        model=model,
                        voice_id=voice,
                        display_name=f"OpenAI {voice}",
                        locale="multi",
                        language="multi",
                        supports_streaming=voice in OPENAI_REALTIME_VOICES,
                        supports_telephony_codec=False,
                        recommended=voice in {"marin", "cedar"},
                    )
                )
        return items

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate one finite audio blob with OpenAI TTS."""
        cleaned = request.text.strip()
        if not cleaned:
            raise VoiceProviderError("No hay texto para generar audio.")
        if request.response_format not in {"mp3", "wav", "opus"}:
            raise VoiceProviderError("Formato de audio no soportado por OpenAI.")
        api_key = self._settings.openai_api_key.get_secret_value().strip()
        if not api_key:
            raise VoiceProviderCredentialError("OPENAI_API_KEY no está configurada.")
        model = request.model or self._settings.openai_tts_model
        if "tts" not in model.lower():
            model = self._settings.openai_tts_model
        payload: dict[str, object] = {
            "model": model,
            "voice": request.voice_id,
            "input": cleaned,
            "response_format": request.response_format,
        }
        if request.instructions and request.instructions.strip():
            payload["instructions"] = request.instructions.strip()
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"OpenAI TTS devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con OpenAI.") from exc
        return TTSResult.from_format(response.content, request.response_format)
