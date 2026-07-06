"""Resemble AI and enterprise voice placeholders."""

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


class ResembleTTSProvider:
    """Configurable Resemble adapter for licensed enterprise voices."""

    provider_id = "resemble"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _api_key(self) -> str:
        return self._settings.resemble_api_key.get_secret_value().strip()

    def _tts_url(self) -> str:
        return self._settings.resemble_tts_url.strip()

    def info(self) -> VoiceProviderInfo:
        """Return safe provider metadata."""
        configured = bool(self._api_key() and self._tts_url())
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Resemble AI",
            configured=configured,
            supports_streaming=True,
            supports_voice_clone=True,
            requires_consent=True,
            notes="Proveedor enterprise: requiere RESEMBLE_API_KEY y RESEMBLE_TTS_URL.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return no public voices; enterprise voices are private/licensed."""
        return []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio through a configured Resemble endpoint."""
        api_key = self._api_key()
        url = self._tts_url()
        if not api_key or not url:
            raise VoiceProviderCredentialError(
                "Configura RESEMBLE_API_KEY y RESEMBLE_TTS_URL para Resemble."
            )
        if not request.voice_id.strip():
            raise VoiceProviderError("Falta voice_id para Resemble.")
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "text": request.text.strip(),
                    "voice_id": request.voice_id.strip(),
                    "model": request.model,
                    "format": request.response_format,
                },
                timeout=45.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Resemble devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con Resemble.") from exc
        content_type = response.headers.get("content-type", "audio/mpeg")
        return TTSResult(audio=response.content, media_type=content_type)


class EnterprisePlaceholderProvider:
    """Non-scraping placeholder for licensed enterprise TTS providers."""

    def __init__(self, provider_id: str, display_name: str) -> None:
        self.provider_id = provider_id
        self._display_name = display_name

    def info(self) -> VoiceProviderInfo:
        """Return disabled enterprise metadata."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name=self._display_name,
            configured=False,
            supports_tts=True,
            supports_streaming=False,
            enabled=True,
            notes=(
                "Proveedor enterprise preparado. Configura vía custom_http o "
                "adapter dedicado con licencia/API oficial."
            ),
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """No public voice catalog is bundled for licensed providers."""
        return []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Refuse synthesis without an official licensed adapter."""
        raise VoiceProviderCredentialError(
            f"{self._display_name} requiere API/licencia oficial configurada."
        )
