"""OpenAI Realtime WebSocket bridge for server-to-server media."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from websockets.asyncio.client import connect

from sip_gateway.audio import (
    OPENAI_INPUT_SAMPLE_RATE,
    SAMPLE_RATE,
    StatefulPcm16Resampler,
)
from sip_gateway.backend import BackendClient, VoiceContext
from sip_gateway.config import GatewaySettings

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
ResponseDoneCallback = Callable[[], Awaitable[None] | None]
_FORBIDDEN_SCHEMA_ROOT_KEYS = {"oneOf", "anyOf", "allOf", "enum", "const", "not"}
_BENIGN_ERROR_CODES = {
    "response_cancel_not_active",
    "conversation_already_has_active_response",
}
_APPOINTMENT_TOOLS = {
    "propose_slots",
    "check_availability",
    "create_appointment",
    "cancel_appointment",
}
_UNCLEAR_FILLERS = {"ah", "eh", "em", "hm", "hmm", "mmm", "ruido", "silencio", "inaudible", "ininteligible"}
_CONFIRMATION_MARKERS = (
    "confirmas", "confirmame", "confirmar", "quieres que la reserve",
    "quiere que la reserve", "queres que a reserve", "te la reservo",
    "reservo la cita", "reservo a cita", "quieres cancelar",
    "quiere cancelar", "queres cancelar",
)
_CONFIRMATION_PHRASES = {
    "si", "vale", "de acuerdo", "correcto", "correcta", "confirmo",
    "adelante", "perfecto", "me viene bien", "esa", "ese",
    "la primera", "el primero", "reservala", "reservalo",
}


def _normalize_user_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_accents.split())


def transcript_is_clear(value: str) -> bool:
    """Reject silence, filler-only and obviously unusable transcriptions."""
    normalized = _normalize_user_text(value)
    if not normalized or any(marker in normalized for marker in ("[inaudible]", "[ruido]", "(ruido)", "...")):
        return False
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens or all(token in _UNCLEAR_FILLERS for token in tokens):
        return False
    if len(tokens) >= 3 and len(set(tokens)) == 1:
        return False
    return sum(character.isalnum() for character in normalized) >= 2


def transcript_has_explicit_confirmation(value: str) -> bool:
    normalized = _normalize_user_text(value)
    if not transcript_is_clear(normalized):
        return False
    if normalized in _CONFIRMATION_PHRASES:
        return True
    return any(phrase in normalized for phrase in _CONFIRMATION_PHRASES if " " in phrase or phrase.startswith("reserva"))


def assistant_requested_confirmation(value: str) -> bool:
    normalized = _normalize_user_text(value)
    return any(marker in normalized for marker in _CONFIRMATION_MARKERS)


def _clarification_instruction(language: str) -> str:
    if _transcription_language(language) == "gl":
        phrase = "Perdoa, non te entendín ben. Podes repetilo?"
    else:
        phrase = "Perdona, no te entendí bien. ¿Puedes repetirlo?"
    return (
        "El último audio no es suficientemente claro. No infieras intención, "
        "servicio, profesional, fecha, hora, nombre, teléfono ni aceptación. "
        "No llames ninguna herramienta. Responde únicamente con esta frase: "
        f'"{phrase}"'
    )


def _sanitize_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    """Remove Realtime-incompatible root schema combinators from tools."""
    sanitized = dict(tool)
    parameters = sanitized.get("parameters")
    if isinstance(parameters, dict):
        sanitized["parameters"] = {
            key: value
            for key, value in parameters.items()
            if key not in _FORBIDDEN_SCHEMA_ROOT_KEYS
        }
        sanitized["parameters"].setdefault("type", "object")
        sanitized["parameters"].setdefault("properties", {})
    return sanitized


def _sanitize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return tool declarations accepted by Realtime GA."""
    return [_sanitize_tool_schema(tool) for tool in tools]


def _transcription_language(value: str) -> str:
    """Return an ISO-639-1 hint accepted by Realtime transcription."""
    normalized = (value or "es").strip().replace("_", "-").split("-", 1)[0]
    return normalized.casefold() or "es"


def build_external_greeting_item(context: VoiceContext) -> dict[str, Any] | None:
    """Build the assistant-history item for a greeting played by external TTS."""
    message = (context.first_message or "").strip()
    if not message or context.voice_provider == "openai":
        return None
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": message}],
        },
    }


def build_realtime_session(context: VoiceContext) -> dict[str, Any]:
    """Build a natural Realtime GA session for one telephone call."""
    external_tts = context.voice_provider != "openai"
    instructions = context.instructions
    if external_tts and (context.first_message or "").strip():
        instructions += (
            "\n\nEl saludo inicial ya fue reproducido por la voz externa. No lo repitas "
            "ni vuelvas a presentarte. Continúa en el mismo idioma del saludo inicial. "
            f"El idioma configurado `{context.language}` orienta la conversación, pero "
            "si el locale de la voz TTS no coincide, prevalece el idioma del saludo; "
            "el locale de la voz TTS no autoriza cambiar de idioma."
        )
    audio_input: dict[str, Any] = {
        "format": {
            "type": "audio/pcm",
            "rate": OPENAI_INPUT_SAMPLE_RATE,
        },
        "noise_reduction": {"type": "near_field"},
        "turn_detection": {
            "type": "server_vad",
            "create_response": not context.transcript_enabled,
            "interrupt_response": context.allow_interruptions,
            "threshold": 0.55,
            "prefix_padding_ms": 300,
            "silence_duration_ms": max(200, min(context.turn_end_silence_ms, 1200)),
        },
    }
    if context.idle_timeout_ms is not None:
        audio_input["turn_detection"]["idle_timeout_ms"] = max(
            5000,
            min(int(context.idle_timeout_ms), 30000),
        )
    if context.transcript_enabled:
        audio_input["transcription"] = {
            "model": "gpt-4o-mini-transcribe",
            "language": _transcription_language(context.language),
            "prompt": (
                "Conversación telefónica con una clínica. Espera nombres propios, "
                "horas, fechas, teléfonos, servicios y profesionales."
            ),
        }

    session: dict[str, Any] = {
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": ["text"] if external_tts else ["audio"],
        "audio": {"input": audio_input},
    }
    if context.model.startswith("gpt-realtime-2"):
        # Low reasoning is the best latency/quality balance for appointment calls.
        session["reasoning"] = {"effort": "low"}
    tools = _sanitize_tools(context.tools)
    if tools:
        session["tools"] = tools
        session["tool_choice"] = "auto"
    if not external_tts:
        session["audio"]["output"] = {
            "format": {"type": "audio/pcm", "rate": OPENAI_INPUT_SAMPLE_RATE},
            "voice": context.realtime_voice,
            "speed": max(0.25, min(float(context.voice_speed), 1.5)),
        }
    return session


class OpenAIRealtimeBridge:
    """Bidirectional audio/text bridge to OpenAI Realtime."""

    def __init__(
        self,
        *,
        settings: GatewaySettings,
        backend: BackendClient,
        context: VoiceContext,
        call_id: str,
        tool_executor: ToolExecutor,
        on_response_done: ResponseDoneCallback | None = None,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._context = context
        self._call_id = call_id
        self._tool_executor = tool_executor
        self._on_response_done = on_response_done
        self.text_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=settings.openai_queue_max_items
        )
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=settings.openai_queue_max_items
        )
        self._ws: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()
        self._first_audio_started_at: float | None = None
        self._started_at = 0.0
        self._input_audio_frames_sent = 0
        self._response_active = False
        self._response_create_inflight = False
        self._response_create_lock = asyncio.Lock()
        self._input_resampler = StatefulPcm16Resampler(
            SAMPLE_RATE, OPENAI_INPUT_SAMPLE_RATE
        )
        self._input_audio_buffer = bytearray()
        self._input_batch_bytes = int(
            OPENAI_INPUT_SAMPLE_RATE * 2 * settings.openai_input_batch_ms / 1000
        )
        self._assistant_text_parts: list[str] = []
        self._processed_tool_call_ids: set[str] = set()
        self._pending_tool_continuation = False
        self._continuation_after_tools = False
        self._last_user_input_clear = not context.transcript_enabled
        self._processed_transcript_item_ids: set[str] = set()

    @property
    def first_audio_latency_ms(self) -> float | None:
        """Return first audio latency in milliseconds."""
        if self._first_audio_started_at is None:
            return None
        return round((self._first_audio_started_at - self._started_at) * 1000, 2)

    @property
    def response_active(self) -> bool:
        """Return whether OpenAI currently has an active response."""
        return self._response_active

    async def start(self) -> None:
        """Open Realtime WebSocket and configure session."""
        self._started_at = time.perf_counter()
        base_url = self._settings.openai_realtime_ws_url.rstrip("?")
        url = f"{base_url}?model={self._context.model}"
        headers = {
            "Authorization": (
                f"Bearer {self._settings.openai_api_key.get_secret_value()}"
            ),
        }
        logger.info(
            "openai_ws_connecting",
            extra={"call_id": self._call_id, "model": self._context.model},
        )
        self._ws = await connect(
            url,
            additional_headers=headers,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        )
        logger.info("openai_ws_connected", extra={"call_id": self._call_id})

        external_tts = self._context.voice_provider != "openai"
        session = build_realtime_session(self._context)
        tools_count = (
            len(session["tools"]) if isinstance(session.get("tools"), list) else 0
        )
        await self._send({"type": "session.update", "session": session})
        logger.info(
            "openai_session_update_sent",
            extra={
                "call_id": self._call_id,
                "external_tts": external_tts,
                "tools_count": tools_count,
                "input_rate": OPENAI_INPUT_SAMPLE_RATE,
                "output_modalities": session["output_modalities"],
                "transcription": self._context.transcript_enabled,
                "temperature_requested": self._context.temperature,
                "temperature_applied": False,
                "turn_end_silence_ms": self._context.turn_end_silence_ms,
                "reasoning_effort": (
                    session.get("reasoning", {}).get("effort")
                    if isinstance(session.get("reasoning"), dict)
                    else None
                ),
            },
        )

        if self._context.first_message:
            if external_tts:
                greeting_item = build_external_greeting_item(self._context)
                if greeting_item is not None:
                    await self._send(greeting_item)
                await self._persist_transcript(
                    "assistant",
                    self._context.first_message,
                    event_id="initial_greeting",
                )
                logger.info(
                    "openai_external_greeting_recorded",
                    extra={"call_id": self._call_id},
                )
            else:
                await self._request_response(
                    instructions=self._context.first_message,
                    output_modalities=["audio"],
                )

        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("openai_bridge_started", extra={"call_id": self._call_id})

    async def send_pcm16(self, pcm16le: bytes) -> None:
        """Resample telephony PCM16/8 kHz and append PCM16/24 kHz to Realtime."""
        if self._ws is None or self._closed.is_set():
            return
        resampled = self._input_resampler.convert(pcm16le)
        self._input_audio_buffer.extend(resampled)
        self._input_audio_frames_sent += 1
        if len(self._input_audio_buffer) < self._input_batch_bytes:
            return
        batch = bytes(self._input_audio_buffer)
        self._input_audio_buffer.clear()
        should_log_audio = (
            self._input_audio_frames_sent <= 4
            or self._input_audio_frames_sent % 50 == 0
        )
        if should_log_audio:
            logger.info(
                "openai_audio_resampled",
                extra={
                    "call_id": self._call_id,
                    "source_rate": SAMPLE_RATE,
                    "target_rate": OPENAI_INPUT_SAMPLE_RATE,
                    "input_bytes": len(pcm16le),
                    "output_bytes": len(batch),
                    "frames_sent": self._input_audio_frames_sent,
                },
            )
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(batch).decode("ascii"),
            }
        )

    async def cancel_response(self) -> bool:
        """Stop the active OpenAI response, avoiding invalid cancel requests."""
        if self._ws is None or self._closed.is_set() or not self._response_active:
            return False
        await self._send({"type": "response.cancel"})
        logger.info("openai_response_cancel_sent", extra={"call_id": self._call_id})
        return True

    async def close(self) -> None:
        """Close WebSocket and stop reader task."""
        self._closed.set()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        if self._ws is not None:
            if self._input_audio_buffer:
                await self._send(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(
                            bytes(self._input_audio_buffer)
                        ).decode("ascii"),
                    }
                )
                self._input_audio_buffer.clear()
            await self._ws.close()
        logger.info("openai_bridge_closed", extra={"call_id": self._call_id})

    async def _send(self, event: dict[str, Any]) -> None:
        if self._ws is None:
            return
        await self._ws.send(json.dumps(event, ensure_ascii=False))

    async def _request_response(
        self,
        *,
        instructions: str | None = None,
        output_modalities: list[str] | None = None,
    ) -> bool:
        """Create one response only when the conversation is ready."""
        async with self._response_create_lock:
            if (
                self._ws is None
                or self._closed.is_set()
                or self._response_active
                or self._response_create_inflight
            ):
                return False
            response: dict[str, Any] = {}
            if instructions:
                response["instructions"] = instructions
            if output_modalities:
                response["output_modalities"] = output_modalities
            self._response_create_inflight = True
            await self._send(
                {
                    "type": "response.create",
                    **({"response": response} if response else {}),
                }
            )
            logger.info(
                "openai_response_create_sent",
                extra={"call_id": self._call_id},
            )
            return True

    def _guard_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Fail closed for appointment tools when the latest speech was unclear."""
        arguments["_server_guard_available"] = bool(self._context.transcript_enabled)
        if not self._context.transcript_enabled:
            return None
        arguments["_server_input_clear"] = self._last_user_input_clear
        if name in _APPOINTMENT_TOOLS and not self._last_user_input_clear:
            return {
                "ok": False,
                "error": "unclear_user_input",
                "message": "El último audio no tiene una transcripción clara.",
                "assistant_guidance": (
                    "No infieras ningún dato ni continúes con la agenda. Pide a la "
                    "persona que repita lo que acaba de decir."
                ),
            }
        return None

    async def _request_validated_turn_response(self, *, clear: bool) -> None:
        await self._request_response(
            instructions=None if clear else _clarification_instruction(self._context.language),
            output_modalities=(
                ["text"] if self._context.voice_provider != "openai" else ["audio"]
            ),
        )

    async def _persist_transcript(
        self,
        role: str,
        text: str,
        *,
        event_id: str | None = None,
    ) -> None:
        if not self._context.transcript_enabled or not text.strip():
            return
        try:
            result = await self._backend.append_transcript(
                call_session_id=self._context.call_session_id,
                role=role,
                text=text.strip(),
                event_id=event_id,
            )
            logger.info(
                "transcript_turn_persisted",
                extra={
                    "call_id": self._call_id,
                    "role": role,
                    "chars": len(text.strip()),
                    "stored": bool(result.get("stored", True)),
                    "reason": result.get("reason"),
                },
            )
        except Exception:
            logger.exception(
                "transcript_persist_failed",
                extra={"call_id": self._call_id, "role": role},
            )

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw_message in self._ws:
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                await self._handle_event(event)
        except Exception:
            if not self._closed.is_set():
                logger.exception(
                    "openai_read_loop_failed",
                    extra={"call_id": self._call_id},
                )
                await self.text_queue.put("__OPENAI_ERROR__")

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "session.created":
            logger.info("openai_session_created", extra={"call_id": self._call_id})
            return
        if event_type == "response.created":
            self._response_active = True
            self._response_create_inflight = False
            self._assistant_text_parts.clear()
            return
        if event_type in {"response.cancelled", "response.failed"}:
            self._response_active = False
            self._response_create_inflight = False

        if event_type == "error":
            raw_error = event.get("error")
            error = raw_error if isinstance(raw_error, dict) else {}
            code = str(error.get("code") or "")
            message = str(error.get("message") or "")
            temperature_compatibility_error = (
                code == "unknown_parameter"
                and (
                    str(error.get("param") or "") == "session.temperature"
                    or "session.temperature" in message
                )
            )
            if code in _BENIGN_ERROR_CODES or temperature_compatibility_error:
                if code == "response_cancel_not_active":
                    self._response_active = False
                elif code == "conversation_already_has_active_response":
                    self._pending_tool_continuation = True
                    self._continuation_after_tools = True
                self._response_create_inflight = False
                logger.warning(
                    "openai_transient_error_ignored",
                    extra={"call_id": self._call_id, "code": code},
                )
                return
            logger.error(
                "openai_error",
                extra={"call_id": self._call_id, "error": raw_error},
            )
            if "session.audio.input.format.rate" in message and "8000" in message:
                await self.text_queue.put("__OPENAI_CONFIG_ERROR_SUPPRESSED__")
                return
            await self.text_queue.put("__OPENAI_ERROR__")
            return

        if event_type in {
            "conversation.item.input_audio_transcription.completed",
            "input_audio_transcription.completed",
        }:
            transcript = event.get("transcript")
            item_id = str(event.get("item_id") or event.get("event_id") or "")
            if item_id and item_id in self._processed_transcript_item_ids:
                return
            if item_id:
                self._processed_transcript_item_ids.add(item_id)
            transcript_text = transcript.strip() if isinstance(transcript, str) else ""
            self._last_user_input_clear = transcript_is_clear(transcript_text)
            if transcript_text:
                await self._persist_transcript("user", transcript_text, event_id=item_id)
            logger.info(
                "user_transcript_completed",
                extra={
                    "call_id": self._call_id,
                    "chars": len(transcript_text),
                    "clear": self._last_user_input_clear,
                },
            )
            if self._context.transcript_enabled:
                await self._request_validated_turn_response(clear=self._last_user_input_clear)
            return

        if event_type in {
            "input_audio_buffer.speech_started",
            "input_audio_buffer.speech_stopped",
        }:
            if event_type == "input_audio_buffer.speech_started" and self._context.transcript_enabled:
                self._last_user_input_clear = False
            logger.info(event_type.replace(".", "_"), extra={"call_id": self._call_id})
            return

        if event_type == "response.output_audio.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                if self._first_audio_started_at is None:
                    self._first_audio_started_at = time.perf_counter()
                await self.audio_queue.put(base64.b64decode(delta))
            return

        if event_type in {
            "response.output_text.delta",
            "response.output_audio_transcript.delta",
        }:
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                self._assistant_text_parts.append(delta)
                await self.text_queue.put(delta)
            return

        if event_type == "response.output_audio_transcript.done":
            transcript = event.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                await self._persist_transcript(
                    "assistant",
                    transcript,
                    event_id=str(event.get("item_id") or event.get("event_id") or ""),
                )
                self._assistant_text_parts.clear()
            return

        if event_type in {
            "response.output_item.done",
            "response.function_call_arguments.done",
        }:
            await self._maybe_handle_tool_call(event)
            return

        if event_type == "response.done":
            self._response_active = False
            self._response_create_inflight = False
            response = event.get("response") if isinstance(event.get("response"), dict) else {}
            response_id = str(response.get("id") or event.get("event_id") or "")
            assistant_text = "".join(self._assistant_text_parts).strip()
            self._assistant_text_parts.clear()
            if assistant_text:
                await self._persist_transcript(
                    "assistant",
                    assistant_text,
                    event_id=response_id,
                )
            logger.info("openai_response_done", extra={"call_id": self._call_id})
            await self.text_queue.put("\n")
            if self._pending_tool_continuation:
                self._pending_tool_continuation = False
                self._continuation_after_tools = False
                await self._request_response(
                    output_modalities=(
                        ["text"]
                        if self._context.voice_provider != "openai"
                        else ["audio"]
                    )
                )
            elif self._on_response_done is not None:
                callback_result = self._on_response_done()
                if asyncio.iscoroutine(callback_result):
                    await callback_result
            return

    async def _maybe_handle_tool_call(self, event: dict[str, Any]) -> None:
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        if not isinstance(item, dict):
            return
        item_type = str(item.get("type") or "")
        if item_type and item_type != "function_call" and "function_call" not in str(event.get("type")):
            return
        name = item.get("name")
        call_id = str(item.get("call_id") or item.get("id") or "")
        arguments_raw = item.get("arguments") or item.get("arguments_json") or "{}"
        if not isinstance(name, str) or not name:
            return
        if not call_id:
            call_id = str(uuid.uuid4())
        if call_id in self._processed_tool_call_ids:
            logger.info(
                "openai_tool_call_duplicate_ignored",
                extra={"call_id": self._call_id, "tool_call_id": call_id},
            )
            return
        self._processed_tool_call_ids.add(call_id)
        try:
            arguments = (
                json.loads(arguments_raw)
                if isinstance(arguments_raw, str)
                else dict(arguments_raw)
            )
        except (TypeError, ValueError):
            arguments = {}

        logger.info(
            "openai_tool_call_started",
            extra={"call_id": self._call_id, "tool": name, "tool_call_id": call_id},
        )
        output = self._guard_tool_call(name, arguments)
        if output is None:
            output = await self._tool_executor(name, arguments)
        else:
            logger.warning(
                "openai_tool_call_blocked_by_voice_guard",
                extra={
                    "call_id": self._call_id,
                    "tool": name,
                    "tool_call_id": call_id,
                    "error": output.get("error"),
                },
            )
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output, ensure_ascii=False, default=str),
                },
            }
        )
        logger.info(
            "openai_tool_output_submitted",
            extra={"call_id": self._call_id, "tool": name, "tool_call_id": call_id},
        )
        if self._response_active:
            self._pending_tool_continuation = True
            self._continuation_after_tools = True
        else:
            await self._request_response(
                output_modalities=(
                    ["text"]
                    if self._context.voice_provider != "openai"
                    else ["audio"]
                )
            )
