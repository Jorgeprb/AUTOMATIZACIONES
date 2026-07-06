"""Google Cloud Text-to-Speech provider."""

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

GOOGLE_STATIC_VOICES = (
    ("es-ES-Standard-A", "Standard A", "es-ES", "es", "female"),
    ("es-ES-Standard-B", "Standard B", "es-ES", "es", "male"),
    ("es-ES-Wavenet-B", "WaveNet B", "es-ES", "es", "male"),
    ("es-ES-Wavenet-C", "WaveNet C", "es-ES", "es", "female"),
    ("es-ES-Neural2-A", "Neural2 A", "es-ES", "es", "female"),
    ("es-ES-Neural2-B", "Neural2 B", "es-ES", "es", "male"),
)

GOOGLE_AUDIO_ENCODINGS = {
    "mp3": "MP3",
    "wav": "LINEAR16",
    "opus": "OGG_OPUS",
}


class GoogleTTSProvider:
    """Google Cloud Text-to-Speech REST provider."""

    provider_id = "google"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _api_key(self) -> str:
        return self._settings.google_tts_api_key.get_secret_value().strip()

    def info(self) -> VoiceProviderInfo:
        """Return provider metadata without exposing secrets."""
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Google Cloud TTS",
            configured=bool(self._api_key()),
            supports_streaming=True,
            notes="Usa catálogo oficial si GOOGLE_TTS_API_KEY está configurada.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return static Google voices and remote catalog when possible."""
        items = [
            VoiceCatalogItem(
                provider=self.provider_id,
                model=voice_id.split("-")[-2] if "-" in voice_id else "google-tts",
                voice_id=voice_id,
                display_name=f"Google {name}",
                locale=locale,
                language=language,
                gender=gender,
                supports_streaming=True,
                supports_telephony_codec=False,
                recommended=voice_id.startswith("es-ES-Neural2"),
            )
            for voice_id, name, locale, language, gender in GOOGLE_STATIC_VOICES
        ]
        api_key = self._api_key()
        if not api_key:
            return items
        try:
            response = httpx.get(
                "https://texttospeech.googleapis.com/v1/voices",
                params={"key": api_key},
                timeout=20.0,
            )
            response.raise_for_status()
            for raw in response.json().get("voices", []):
                names = raw.get("name")
                language_codes = raw.get("languageCodes")
                if not isinstance(names, str) or not names:
                    continue
                locale = (
                    language_codes[0]
                    if isinstance(language_codes, list) and language_codes
                    else None
                )
                gender = raw.get("ssmlGender")
                items.append(
                    VoiceCatalogItem(
                        provider=self.provider_id,
                        model=names.split("-")[-2] if "-" in names else "google-tts",
                        voice_id=names,
                        display_name=f"Google {names}",
                        locale=locale,
                        language=(locale.split("-", maxsplit=1)[0] if locale else None),
                        gender=gender.lower() if isinstance(gender, str) else None,
                        supports_streaming=True,
                    )
                )
        except (httpx.HTTPError, ValueError):
            return items
        return list({(item.model, item.voice_id): item for item in items}.values())

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio using Google Cloud Text-to-Speech."""
        api_key = self._api_key()
        if not api_key:
            raise VoiceProviderCredentialError(
                "GOOGLE_TTS_API_KEY no está configurada."
            )
        voice_id = request.voice_id.strip()
        if not voice_id:
            raise VoiceProviderError("Falta voice_id para Google TTS.")
        locale = request.locale or "-".join(voice_id.split("-")[:2]) or "es-ES"
        payload = {
            "input": {"text": request.text.strip()},
            "voice": {"languageCode": locale, "name": voice_id},
            "audioConfig": {
                "audioEncoding": GOOGLE_AUDIO_ENCODINGS.get(
                    request.response_format,
                    "MP3",
                ),
                "speakingRate": float(request.voice_speed),
                "pitch": float(request.voice_pitch),
            },
        }
        try:
            response = httpx.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                params={"key": api_key},
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            audio_content = data.get("audioContent")
            if not isinstance(audio_content, str) or not audio_content:
                raise VoiceProviderError("Google TTS no devolvió audio.")
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Google TTS devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con Google.") from exc
        return TTSResult.from_format(
            base64.b64decode(audio_content),
            request.response_format,
        )
