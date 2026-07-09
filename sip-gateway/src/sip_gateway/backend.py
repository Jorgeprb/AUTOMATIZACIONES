"""HTTP client for the FastAPI backend internal voice endpoints."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import httpx

from sip_gateway.config import GatewaySettings


@dataclass(frozen=True, slots=True)
class VoiceContext:
    """Assistant context resolved by backend."""

    clinic_id: str
    call_session_id: str
    phone_number_id: str | None
    assistant_config_id: str
    model: str
    realtime_voice: str
    voice_provider: str
    tts_model: str | None
    voice_id: str | None
    voice_locale: str | None
    voice_gender: str | None
    azure_speech_region: str | None
    voice_style: str | None
    voice_speed: str
    voice_pitch: str
    voice_stability: str | None
    voice_similarity: str | None
    voice_temperature: str | None
    output_audio_format: str
    telephony_codec: str
    preview_audio_format: str
    allow_interruptions: bool
    idle_timeout_ms: int | None
    transcript_enabled: bool
    first_message: str
    instructions: str
    tools: list[dict[str, Any]]
    call_audio_mode: str = "vps_media_bridge"
    openai_project_id: str | None = None
    prompt: str | None = None
    caller: str | None = None
    called_number: str | None = None
    resolved_called_number: str | None = None
    clinic: dict[str, Any] | None = None

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> VoiceContext:
        """Build context while ignoring backend fields unknown to this client."""
        allowed = {field.name for field in fields(cls)}
        filtered = {key: value for key, value in data.items() if key in allowed}
        if not filtered.get("prompt"):
            filtered["prompt"] = filtered.get("instructions")
        filtered["telephony_codec"] = str(
            filtered.get("telephony_codec") or "pcmu"
        ).casefold()
        return cls(**filtered)


@dataclass(frozen=True, slots=True)
class TTSAudio:
    """One audio response from backend TTS."""

    audio: bytes
    media_type: str


class BackendRequestError(RuntimeError):
    """Backend rejected an internal gateway request."""

    def __init__(self, *, endpoint: str, status_code: int, detail: Any) -> None:
        self.endpoint = endpoint
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"backend {endpoint} returned HTTP {status_code}: {detail}")


def _response_detail(response: httpx.Response) -> Any:
    """Return a log-safe backend error body."""
    try:
        return response.json()
    except ValueError:
        return response.text[:500]


def _preview_format_for_call(context: VoiceContext) -> str:
    """Ask backend providers for raw G.711 when this is a telephony call."""
    if context.telephony_codec in {"pcma", "pcmu"}:
        return "wav"
    return context.preview_audio_format or "wav"


class BackendClient:
    """Small async client to keep gateway decoupled from FastAPI internals."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._settings.internal_api_key is not None:
            headers["X-Internal-API-Key"] = (
                self._settings.internal_api_key.get_secret_value()
            )
        return headers

    def _build_context_payload(
        self,
        *,
        called_number: str,
        caller_phone: str,
        openai_call_id: str,
        provider_call_id: str,
        caller: str | None = None,
        callee: str | None = None,
        sip_to: str | None = None,
        sip_from: str | None = None,
    ) -> dict[str, Any]:
        """Build the backend context payload without exposing secrets."""
        return {
            "called_number": called_number,
            "caller_phone": caller_phone,
            "caller": caller or caller_phone,
            "callee": callee or called_number,
            "sip_to": sip_to,
            "sip_from": sip_from,
            "openai_call_id": openai_call_id,
            "provider_call_id": provider_call_id,
        }

    async def resolve_voice_context(
        self,
        *,
        called_number: str,
        caller_phone: str,
        openai_call_id: str,
        provider_call_id: str,
        caller: str | None = None,
        callee: str | None = None,
        sip_to: str | None = None,
        sip_from: str | None = None,
    ) -> VoiceContext:
        """Resolve called DID to clinic prompt/config through backend."""
        payload = self._build_context_payload(
            called_number=called_number,
            caller_phone=caller_phone,
            caller=caller,
            callee=callee,
            sip_to=sip_to,
            sip_from=sip_from,
            openai_call_id=openai_call_id,
            provider_call_id=provider_call_id,
        )
        endpoint = f"{self._settings.backend_internal_url}/api/internal/voice/context"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers=self._headers(),
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BackendRequestError(
                endpoint="/api/internal/voice/context",
                status_code=response.status_code,
                detail=_response_detail(response),
            ) from exc
        return VoiceContext.from_response(response.json())

    async def synthesize_tts(
        self,
        *,
        context: VoiceContext,
        text: str,
    ) -> TTSAudio:
        """Generate one TTS chunk through backend provider layer."""
        payload = {
            "clinic_id": context.clinic_id,
            "text": text,
            "voice_provider": context.voice_provider,
            "realtime_voice": context.realtime_voice,
            "tts_model": context.tts_model,
            "voice_id": context.voice_id,
            "voice_locale": context.voice_locale,
            "voice_gender": context.voice_gender,
            "azure_speech_region": context.azure_speech_region,
            "voice_style": context.voice_style,
            "voice_speed": context.voice_speed,
            "voice_pitch": context.voice_pitch,
            "voice_stability": context.voice_stability,
            "voice_similarity": context.voice_similarity,
            "voice_temperature": context.voice_temperature,
            "output_audio_format": context.telephony_codec,
            "telephony_codec": context.telephony_codec,
            "preview_audio_format": _preview_format_for_call(context),
            "call_audio_mode": context.call_audio_mode,
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{self._settings.backend_internal_url}/api/internal/voice/tts",
                json=payload,
                headers=self._headers(),
            )
        response.raise_for_status()
        return TTSAudio(
            audio=response.content,
            media_type=response.headers.get(
                "content-type",
                "application/octet-stream",
            ).split(";", maxsplit=1)[0],
        )

    async def execute_tool(
        self,
        *,
        clinic_id: str,
        call_session_id: str | None,
        openai_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a model tool via backend production dispatcher."""
        payload = {
            "clinic_id": clinic_id,
            "call_session_id": call_session_id,
            "openai_call_id": openai_call_id,
            "name": name,
            "arguments": arguments,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._settings.backend_internal_url}/api/internal/voice/tool",
                json=payload,
                headers=self._headers(),
            )
        response.raise_for_status()
        return response.json()
