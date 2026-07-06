"""ElevenLabs TTS provider using official HTTP APIs."""

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

ELEVENLABS_DEFAULT_MODEL = "eleven_multilingual_v2"


class ElevenLabsTTSProvider:
    """Finite ElevenLabs TTS adapter.

    Voice cloning is intentionally not automated here. Custom/cloned voices can
    be used only by explicit ``voice_id`` and are marked as requiring consent.
    """

    provider_id = "elevenlabs"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _api_key(self) -> str:
        return self._settings.elevenlabs_api_key.get_secret_value().strip()

    def info(self) -> VoiceProviderInfo:
        """Return public metadata without exposing credentials."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="ElevenLabs",
            configured=bool(self._api_key()),
            supports_streaming=True,
            supports_voice_clone=True,
            requires_consent=True,
            notes="Requiere ELEVENLABS_API_KEY para catálogo remoto y preview.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Fetch available voices from ElevenLabs when credentials exist."""
        api_key = self._api_key()
        if not api_key:
            return []
        try:
            response = httpx.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": api_key},
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        items: list[VoiceCatalogItem] = []
        for raw in response.json().get("voices", []):
            voice_id = raw.get("voice_id")
            name = raw.get("name")
            if not isinstance(voice_id, str) or not isinstance(name, str):
                continue
            labels = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
            locale = labels.get("language") if isinstance(labels, dict) else None
            gender = labels.get("gender") if isinstance(labels, dict) else None
            items.append(
                VoiceCatalogItem(
                    provider=self.provider_id,
                    model=ELEVENLABS_DEFAULT_MODEL,
                    voice_id=voice_id,
                    display_name=f"ElevenLabs {name}",
                    locale=locale if isinstance(locale, str) else None,
                    language=locale if isinstance(locale, str) else None,
                    gender=gender if isinstance(gender, str) else None,
                    supports_streaming=True,
                    supports_voice_clone=True,
                    requires_consent=True,
                )
            )
        return items

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio using ElevenLabs text-to-speech."""
        api_key = self._api_key()
        if not api_key:
            raise VoiceProviderCredentialError(
                "ELEVENLABS_API_KEY no está configurada."
            )
        voice_id = request.voice_id.strip()
        if not voice_id:
            raise VoiceProviderError("Falta voice_id para ElevenLabs.")
        payload: dict[str, object] = {
            "text": request.text.strip(),
            "model_id": request.model or ELEVENLABS_DEFAULT_MODEL,
        }
        settings: dict[str, float] = {}
        if request.voice_stability is not None:
            settings["stability"] = float(request.voice_stability)
        if request.voice_similarity is not None:
            settings["similarity_boost"] = float(request.voice_similarity)
        if request.voice_speed != 1:
            settings["speed"] = float(request.voice_speed)
        if settings:
            payload["voice_settings"] = settings
        try:
            response = httpx.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
                json=payload,
                timeout=40.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"ElevenLabs devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError(
                "No se pudo generar audio con ElevenLabs."
            ) from exc
        return TTSResult(audio=response.content, media_type="audio/mpeg")
