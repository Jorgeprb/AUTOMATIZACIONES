"""Small finite audio generation helpers backed by voice providers."""

from __future__ import annotations

from decimal import Decimal

from app.config import Settings
from app.voice_providers import get_voice_provider
from app.voice_providers.base import TTSRequest, TTSResult, VoiceProviderError


class TTSGenerationError(RuntimeError):
    """Raised when a one-shot text-to-speech preview cannot be generated."""


def synthesize_speech(
    settings: Settings,
    *,
    provider: str,
    text: str,
    voice: str,
    model: str | None = None,
    instructions: str | None = None,
    response_format: str = "mp3",
    output_audio_format: str = "pcm16",
    telephony_codec: str = "pcmu",
    locale: str | None = None,
    gender: str | None = None,
    provider_region: str | None = None,
    voice_style: str | None = None,
    voice_speed: Decimal = Decimal("1.00"),
    voice_pitch: Decimal = Decimal("0.00"),
    voice_stability: Decimal | None = None,
    voice_similarity: Decimal | None = None,
    voice_temperature: Decimal | None = None,
) -> TTSResult:
    """Generate finite TTS through the selected provider and close resources."""
    cleaned = text.strip()
    if not cleaned:
        raise TTSGenerationError("No hay texto para generar audio.")
    if response_format not in {"mp3", "wav", "opus"}:
        raise TTSGenerationError("Formato de audio no soportado.")
    try:
        adapter = get_voice_provider(settings, provider)
    except KeyError as exc:
        raise TTSGenerationError(f"Proveedor de voz no soportado: {provider}.") from exc
    try:
        return adapter.synthesize(
            TTSRequest(
                text=cleaned,
                provider=provider,
                model=model,
                voice_id=voice,
                instructions=instructions,
                response_format=response_format,
                output_audio_format=output_audio_format,
                telephony_codec=telephony_codec,
                locale=locale,
                gender=gender,
                provider_region=provider_region,
                voice_style=voice_style,
                voice_speed=voice_speed,
                voice_pitch=voice_pitch,
                voice_stability=voice_stability,
                voice_similarity=voice_similarity,
                voice_temperature=voice_temperature,
            )
        )
    except VoiceProviderError as exc:
        raise TTSGenerationError(str(exc)) from exc


def synthesize_openai_speech(
    settings: Settings,
    *,
    text: str,
    voice: str,
    model: str | None = None,
    instructions: str | None = None,
    response_format: str = "mp3",
) -> bytes:
    """Backward-compatible OpenAI wrapper used by existing code/tests."""
    return synthesize_speech(
        settings,
        provider="openai",
        text=text,
        voice=voice,
        model=model,
        instructions=instructions,
        response_format=response_format,
    ).audio
