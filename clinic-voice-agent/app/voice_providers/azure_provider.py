"""Azure Speech TTS provider."""

from __future__ import annotations

import html
from collections.abc import Iterator
from decimal import Decimal

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

AZURE_STATIC_VOICES = (
    ("gl-ES-SabelaNeural", "Sabela Neural", "gl-ES", "gl", "female"),
    ("gl-ES-RoiNeural", "Roi Neural", "gl-ES", "gl", "male"),
    ("es-ES-ElviraNeural", "Elvira Neural", "es-ES", "es", "female"),
    ("es-ES-AlvaroNeural", "Álvaro Neural", "es-ES", "es", "male"),
    ("es-ES-AbrilNeural", "Abril Neural", "es-ES", "es", "female"),
    ("es-ES-ArnauNeural", "Arnau Neural", "es-ES", "es", "male"),
    ("es-ES-DarioNeural", "Dario Neural", "es-ES", "es", "male"),
    ("es-ES-EliasNeural", "Elias Neural", "es-ES", "es", "male"),
    ("es-ES-EstrellaNeural", "Estrella Neural", "es-ES", "es", "female"),
    ("es-ES-IreneNeural", "Irene Neural", "es-ES", "es", "female"),
    ("es-ES-LaiaNeural", "Laia Neural", "es-ES", "es", "female"),
    ("es-ES-LiaNeural", "Lia Neural", "es-ES", "es", "female"),
    ("es-ES-NilNeural", "Nil Neural", "es-ES", "es", "male"),
    ("es-ES-SaulNeural", "Saul Neural", "es-ES", "es", "male"),
    ("es-ES-TeoNeural", "Teo Neural", "es-ES", "es", "male"),
    ("es-ES-TrianaNeural", "Triana Neural", "es-ES", "es", "female"),
    ("es-ES-VeraNeural", "Vera Neural", "es-ES", "es", "female"),
    ("es-ES-XimenaNeural", "Ximena Neural", "es-ES", "es", "female"),
)

_AZURE_HTTP_CLIENT = httpx.Client(
    timeout=httpx.Timeout(30.0, connect=5.0),
    limits=httpx.Limits(
        max_connections=50, max_keepalive_connections=20, keepalive_expiry=60.0
    ),
    headers={"User-Agent": "clinic-voice-agent"},
)

AZURE_OUTPUT_FORMATS = {
    "mp3": "audio-24khz-48kbitrate-mono-mp3",
    "wav": "riff-24khz-16bit-mono-pcm",
    "opus": "ogg-24khz-16bit-mono-opus",
    "pcmu": "raw-8khz-8bit-mono-mulaw",
    "pcma": "raw-8khz-8bit-mono-alaw",
    "pcm16": "riff-8khz-16bit-mono-pcm",
}


class AzureTTSProvider:
    """Azure Cognitive Services Speech provider."""

    provider_id = "azure"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _key(self) -> str:
        return self._settings.azure_speech_key.get_secret_value().strip()

    def _region(self, override: str | None = None) -> str:
        return (override or self._settings.azure_speech_region).strip()

    def info(self) -> VoiceProviderInfo:
        """Return provider metadata without exposing secrets."""
        configured = bool(self._key() and self._region())
        return VoiceProviderInfo(
            id=self.provider_id,
            display_name="Azure Speech",
            configured=configured,
            supports_streaming=True,
            supports_telephony_codec=True,
            notes="Soporta voces gallegas y formatos G.711 en regiones compatibles.",
        )

    def catalog(self) -> list[VoiceCatalogItem]:
        """Return static Azure voices and remote voices when credentials exist."""
        items = [
            VoiceCatalogItem(
                provider=self.provider_id,
                model="azure-neural",
                voice_id=voice_id,
                display_name=f"Azure {name}",
                locale=locale,
                language=language,
                gender=gender,
                supports_streaming=True,
                supports_telephony_codec=True,
                recommended=voice_id in {"gl-ES-SabelaNeural", "gl-ES-RoiNeural"},
            )
            for voice_id, name, locale, language, gender in AZURE_STATIC_VOICES
        ]
        if not self.info().configured:
            return items
        try:
            response = _AZURE_HTTP_CLIENT.get(
                f"https://{self._region()}.tts.speech.microsoft.com/"
                "cognitiveservices/voices/list",
                headers={"Ocp-Apim-Subscription-Key": self._key()},
                timeout=20.0,
            )
            response.raise_for_status()
            for raw in response.json():
                short_name = raw.get("ShortName")
                if not isinstance(short_name, str) or not short_name:
                    continue
                locale = (
                    raw.get("Locale") if isinstance(raw.get("Locale"), str) else None
                )
                gender = (
                    raw.get("Gender") if isinstance(raw.get("Gender"), str) else None
                )
                display = raw.get("DisplayName")
                items.append(
                    VoiceCatalogItem(
                        provider=self.provider_id,
                        model="azure-neural",
                        voice_id=short_name,
                        display_name=f"Azure {display or short_name}",
                        locale=locale,
                        language=(locale.split("-", maxsplit=1)[0] if locale else None),
                        gender=gender.lower() if gender else None,
                        supports_streaming=True,
                        supports_telephony_codec=True,
                    )
                )
        except (httpx.HTTPError, ValueError):
            return items
        return list({(item.model, item.voice_id): item for item in items}.values())

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate finite audio using Azure Speech SSML."""
        key = self._key()
        region = self._region(request.provider_region)
        if not key or not region:
            raise VoiceProviderCredentialError(
                "AZURE_SPEECH_KEY y AZURE_SPEECH_REGION deben estar configuradas."
            )
        raw_codec = request.response_format == "wav" and request.telephony_codec in {
            "pcma",
            "pcmu",
        }
        output_format = AZURE_OUTPUT_FORMATS.get(
            request.telephony_codec if raw_codec else request.response_format,
            AZURE_OUTPUT_FORMATS["mp3"],
        )
        voice_id = request.voice_id.strip()
        escaped = html.escape(request.text.strip())
        if not voice_id:
            raise VoiceProviderError("Falta voice_id para Azure Speech.")
        style = (request.voice_style or "").strip()
        speed = max(Decimal("0.50"), min(request.voice_speed, Decimal("2.00")))
        pitch = max(Decimal("-24.00"), min(request.voice_pitch, Decimal("24.00")))
        pitch_value = f"{pitch:+.2f}st"
        escaped_text = (
            f"<prosody rate='{speed:.2f}' pitch='{pitch_value}'>{escaped}</prosody>"
        )
        if style:
            escaped_text = (
                "<mstts:express-as style='"
                f"{html.escape(style)}'>{escaped_text}</mstts:express-as>"
            )
        ssml = (
            "<speak version='1.0' "
            "xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='"
            f"{html.escape(request.locale or 'es-ES')}'>"
            f"<voice name='{html.escape(voice_id)}'>{escaped_text}</voice></speak>"
        )
        try:
            response = _AZURE_HTTP_CLIENT.post(
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": output_format,
                },
                content=ssml.encode("utf-8"),
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise VoiceProviderError(
                f"Azure Speech devolvió HTTP {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError("No se pudo generar audio con Azure.") from exc
        if raw_codec:
            media_type = (
                "audio/pcma" if request.telephony_codec == "pcma" else "audio/pcmu"
            )
            return TTSResult(audio=response.content, media_type=media_type)
        return TTSResult.from_format(response.content, request.response_format)

    def preview(self, request: TTSRequest) -> TTSResult:
        """Generate one finite preview audio."""
        return self.synthesize(request)

    def synthesize_stream(self, request: TTSRequest) -> Iterator[bytes]:
        """Yield one finite Azure chunk; streaming can be added later."""
        yield self.synthesize(request).audio

    def get_voice_catalog(self) -> list[VoiceCatalogItem]:
        """Return catalog using provider-neutral name."""
        return self.catalog()
