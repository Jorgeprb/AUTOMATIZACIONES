"""Small finite audio generation helpers."""

from __future__ import annotations

import httpx

from app.config import Settings


class TTSGenerationError(RuntimeError):
    """Raised when a one-shot text-to-speech preview cannot be generated."""


def _select_speech_model(settings: Settings, requested_model: str | None) -> str:
    """Use a real speech model, falling back when a Realtime model is provided."""
    if requested_model and "tts" in requested_model.lower():
        return requested_model
    return settings.openai_tts_model


def synthesize_openai_speech(
    settings: Settings,
    *,
    text: str,
    voice: str,
    model: str | None = None,
    instructions: str | None = None,
    response_format: str = "mp3",
) -> bytes:
    """Generate one finite audio blob with OpenAI TTS and close the connection."""
    cleaned = text.strip()
    if not cleaned:
        raise TTSGenerationError("No hay texto para generar audio.")
    if response_format not in {"mp3", "wav", "opus"}:
        raise TTSGenerationError("Formato de audio no soportado.")

    api_key = settings.openai_api_key.get_secret_value().strip()
    if not api_key:
        raise TTSGenerationError("OPENAI_API_KEY no está configurada.")

    payload = {
        "model": _select_speech_model(settings, model),
        "voice": voice,
        "input": cleaned,
        "response_format": response_format,
    }
    if instructions and instructions.strip():
        payload["instructions"] = instructions.strip()
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.content
    except httpx.HTTPStatusError as exc:
        raise TTSGenerationError(
            f"OpenAI TTS devolvió HTTP {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        raise TTSGenerationError("No se pudo generar audio TTS.") from exc
