"""Custom HTTP TTS provider for licensed/private integrations."""

from __future__ import annotations

import base64

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


class CustomHTTPTTSProvider:
    """Generic custom HTTP adapter.

    This is intentionally simple: the configured endpoint receives JSON and can
    return either raw audio or ``{"audio_base64": "..."}``.
    """

    provider_id = "custom_http"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _url(self) -> str:
        return self._settings.custom_http_tts_url.strip()

    def _api_key(self) -> str:
        return self._settings.custom_http_tts_api_key.get_secret_value().strip()

    def info(self) -> VoiceProviderInfo:
        """Return safe provider metadata."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Custom HTTP TTS",
            configured=bool(self._url()),
            supports_streaming=False,
            supports_voice_clone=True,
            requires_consent=True,
            notes="Endpoint propio/licenciado. No se conecta a demos no autorizadas.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Custom endpoints do not expose a standard voice catalog."""
        return []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate audio using the configured custom endpoint."""
        url = self._url()
        if not url:
            raise VoiceProviderCredentialError(
                "CUSTOM_HTTP_TTS_URL no está configurada."
            )
        headers = {"Content-Type": "application/json"}
        api_key = self._api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = httpx.post(
                url,
                headers=headers,
                json={
                    "text": request.text.strip(),
                    "provider": request.provider,
                    "model": request.model,
                    "voice_id": request.voice_id,
                    "locale": request.locale,
                    "format": request.response_format,
                    "voice_speed": float(request.voice_speed),
                    "voice_pitch": float(request.voice_pitch),
                    "instructions": request.instructions,
                },
                timeout=45.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Custom HTTP TTS devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError(
                "No se pudo generar audio con Custom HTTP."
            ) from exc

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            audio_base64 = response.json().get("audio_base64")
            if not isinstance(audio_base64, str) or not audio_base64:
                raise VoiceProviderError(
                    "Custom HTTP TTS devolvió JSON sin audio_base64."
                )
            return TTSResult.from_format(
                base64.b64decode(audio_base64),
                request.response_format,
            )
        return TTSResult(
            audio=response.content,
            media_type=content_type or "audio/mpeg",
        )
