"""Amazon Polly TTS provider."""

from __future__ import annotations

import importlib
from typing import Any

from app.config import Settings
from app.voice_providers.base import (
    TTSRequest,
    TTSResult,
    VoiceCatalogItem,
    VoiceProviderCredentialError,
    VoiceProviderError,
    VoiceProviderInfo,
)

POLLY_ES_VOICES = (
    ("Lucia", "Lucía", "es-ES", "es", "female"),
    ("Sergio", "Sergio", "es-ES", "es", "male"),
    ("Alba", "Alba", "es-ES", "es", "female"),
    ("Enrique", "Enrique", "es-ES", "es", "male"),
    ("Raul", "Raúl", "es-ES", "es", "male"),
    ("Conchita", "Conchita", "es-ES", "es", "female"),
)


class AmazonPollyTTSProvider:
    """Finite Amazon Polly adapter.

    Boto3 is imported lazily so local development can run without AWS SDK
    unless Polly is actually used.
    """

    provider_id = "amazon_polly"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _configured(self) -> bool:
        return bool(self._settings.amazon_polly_region.strip())

    def info(self) -> VoiceProviderInfo:
        """Return safe provider metadata."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Amazon Polly",
            configured=self._configured(),
            supports_streaming=False,
            notes="Usa credenciales AWS estándar y AMAZON_POLLY_REGION.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return Spanish static Polly voices."""
        return [
            VoiceCatalogItem(
                provider=self.provider_id,
                model="neural",
                voice_id=voice_id,
                display_name=f"Amazon Polly {name}",
                locale=locale,
                language=language,
                gender=gender,
                supports_telephony_codec=True,
                recommended=voice_id in {"Lucia", "Sergio"},
            )
            for voice_id, name, locale, language, gender in POLLY_ES_VOICES
        ]

    def _client(self) -> Any:
        if not self._settings.amazon_polly_region.strip():
            raise VoiceProviderCredentialError(
                "AMAZON_POLLY_REGION no está configurada."
            )
        try:
            boto3: Any = importlib.import_module("boto3")
        except ImportError as exc:
            raise VoiceProviderCredentialError(
                "boto3 no está instalado; no se puede usar Amazon Polly."
            ) from exc
        return boto3.client("polly", region_name=self._settings.amazon_polly_region)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio using Amazon Polly."""
        voice_id = request.voice_id.strip()
        if not voice_id:
            raise VoiceProviderError("Falta voice_id para Amazon Polly.")
        output_format = "mp3"
        media_type = "audio/mpeg"
        if request.response_format == "opus":
            output_format = "ogg_vorbis"
            media_type = "audio/ogg"
        elif request.response_format == "wav":
            output_format = "pcm"
            media_type = "audio/wav"
        try:
            response = self._client().synthesize_speech(
                Text=request.text.strip(),
                VoiceId=voice_id,
                Engine=request.model or "neural",
                OutputFormat=output_format,
            )
            stream = response.get("AudioStream")
            if stream is None:
                raise VoiceProviderError("Amazon Polly no devolvió AudioStream.")
            audio = stream.read()
        except VoiceProviderError:
            raise
        except Exception as exc:
            raise VoiceProviderError(
                "No se pudo generar audio con Amazon Polly."
            ) from exc
        return TTSResult(audio=audio, media_type=media_type)
