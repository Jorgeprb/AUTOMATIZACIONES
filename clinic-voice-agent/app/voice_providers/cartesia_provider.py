"""Cartesia TTS provider."""

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

CARTESIA_STATIC_VOICES = (
    ("cartesia-sonic-es", "Sonic español", "es-ES", "es", None),
)


class CartesiaTTSProvider:
    """Finite Cartesia TTS adapter."""

    provider_id = "cartesia"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _api_key(self) -> str:
        return self._settings.cartesia_api_key.get_secret_value().strip()

    def info(self) -> VoiceProviderInfo:
        """Return safe provider metadata."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Cartesia",
            configured=bool(self._api_key()),
            supports_streaming=True,
            supports_stt=True,
            notes="Requiere CARTESIA_API_KEY para preview.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return a minimal initial catalog; sync can be extended later."""
        return [
            VoiceCatalogItem(
                provider=self.provider_id,
                model="sonic-2",
                voice_id=voice_id,
                display_name=f"Cartesia {name}",
                locale=locale,
                language=language,
                gender=gender,
                supports_streaming=True,
                recommended=language == "es",
            )
            for voice_id, name, locale, language, gender in CARTESIA_STATIC_VOICES
        ]

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio through Cartesia bytes endpoint."""
        api_key = self._api_key()
        if not api_key:
            raise VoiceProviderCredentialError("CARTESIA_API_KEY no está configurada.")
        voice_id = request.voice_id.strip()
        if not voice_id:
            raise VoiceProviderError("Falta voice_id para Cartesia.")
        payload = {
            "model_id": request.model or "sonic-2",
            "transcript": request.text.strip(),
            "voice": {"mode": "id", "id": voice_id},
            "language": (request.locale or "es-ES").split("-", maxsplit=1)[0],
            "output_format": {
                "container": "mp3",
                "encoding": "mp3",
                "sample_rate": 44100,
            },
        }
        try:
            response = httpx.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": api_key,
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=40.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Cartesia devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con Cartesia.") from exc
        return TTSResult(audio=response.content, media_type="audio/mpeg")
