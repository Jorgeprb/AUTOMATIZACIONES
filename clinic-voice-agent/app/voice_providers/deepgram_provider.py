"""Deepgram Aura TTS provider."""

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

DEEPGRAM_STATIC_VOICES = (
    ("aura-2-thalia-es", "Thalia ES", "es-ES", "es", "female"),
    ("aura-2-andromeda-en", "Andromeda EN", "en-US", "en", "female"),
    ("aura-asteria-en", "Asteria EN", "en-US", "en", "female"),
)


class DeepgramTTSProvider:
    """Finite Deepgram Speak adapter."""

    provider_id = "deepgram"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _api_key(self) -> str:
        return self._settings.deepgram_api_key.get_secret_value().strip()

    def info(self) -> VoiceProviderInfo:
        """Return provider metadata."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Deepgram Aura",
            configured=bool(self._api_key()),
            supports_streaming=True,
            supports_stt=True,
            notes="Requiere DEEPGRAM_API_KEY para preview.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return initial Aura voices."""
        return [
            VoiceCatalogItem(
                provider=self.provider_id,
                model=voice_id,
                voice_id=voice_id,
                display_name=f"Deepgram {name}",
                locale=locale,
                language=language,
                gender=gender,
                supports_streaming=True,
                recommended=language == "es",
            )
            for voice_id, name, locale, language, gender in DEEPGRAM_STATIC_VOICES
        ]

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio through Deepgram Speak."""
        api_key = self._api_key()
        if not api_key:
            raise VoiceProviderCredentialError("DEEPGRAM_API_KEY no está configurada.")
        model = (request.model or request.voice_id or "aura-2-thalia-es").strip()
        try:
            response = httpx.post(
                "https://api.deepgram.com/v1/speak",
                params={"model": model},
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": request.text.strip()},
                timeout=40.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Deepgram devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con Deepgram.") from exc
        return TTSResult(audio=response.content, media_type="audio/mpeg")
