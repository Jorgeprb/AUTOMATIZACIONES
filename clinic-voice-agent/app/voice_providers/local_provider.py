"""Local open-source TTS adapters, disabled unless a local service exists."""

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

LOCAL_MODELS = {
    "local_coqui": "Coqui XTTS-v2",
    "local_chatterbox": "Chatterbox",
}


class LocalTTSProvider:
    """Adapter for a locally hosted TTS HTTP service."""

    def __init__(self, settings: Settings, provider_id: str) -> None:
        self._settings = settings
        self.provider_id = provider_id

    def _base_url(self) -> str:
        return self._settings.local_tts_base_url.strip().rstrip("/")

    def info(self) -> VoiceProviderInfo:
        """Return safe provider metadata."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name=LOCAL_MODELS[self.provider_id],
            configured=bool(self._base_url()),
            supports_streaming=False,
            supports_voice_clone=True,
            requires_consent=True,
            notes=(
                "Desactivado salvo que LOCAL_TTS_BASE_URL apunte a un "
                "servicio local."
            ),
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return a generic local voice placeholder when local service exists."""
        if not self._base_url():
            return []
        return [
            VoiceCatalogItem(
                provider=self.provider_id,
                model=self.provider_id,
                voice_id="default",
                display_name=f"{LOCAL_MODELS[self.provider_id]} default",
                supports_voice_clone=True,
                requires_consent=True,
            )
        ]

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate audio through the local service."""
        base_url = self._base_url()
        if not base_url:
            raise VoiceProviderCredentialError(
                "LOCAL_TTS_BASE_URL no está configurada."
            )
        try:
            response = httpx.post(
                f"{base_url}/tts",
                json={
                    "provider": self.provider_id,
                    "text": request.text.strip(),
                    "model": request.model or self.provider_id,
                    "voice_id": request.voice_id or "default",
                    "format": request.response_format,
                    "voice_speed": float(request.voice_speed),
                    "voice_pitch": float(request.voice_pitch),
                    "instructions": request.instructions,
                },
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Local TTS devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con Local TTS.") from exc
        return TTSResult(
            audio=response.content,
            media_type=response.headers.get("content-type", "audio/mpeg"),
        )
