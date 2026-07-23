"""OpenAI Realtime WebSocket bridge for server-to-server media."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
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
_FORBIDDEN_SCHEMA_ROOT_KEYS = {"oneOf", "anyOf", "allOf", "enum", "const", "not"}


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


def build_external_greeting_item(context: VoiceContext) -> dict[str, Any] | None:
    """Represent an externally played greeting in the Realtime conversation."""
    if context.voice_provider == "openai" or not context.first_message.strip():
        return None
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": context.first_message,
                }
            ],
        },
    }


def _supports_reasoning_model(model: str) -> bool:
    return model.strip().casefold().startswith("gpt-realtime-2")


def _build_turn_detection(
    context: VoiceContext,
    settings: GatewaySettings | None,
) -> dict[str, Any]:
    mode = settings.realtime_vad_mode if settings is not None else "server_vad"
    common: dict[str, Any] = {
        "type": mode,
        "create_response": True,
        "interrupt_response": context.allow_interruptions,
    }
    if mode == "semantic_vad":
        common["eagerness"] = (
            settings.realtime_vad_eagerness if settings is not None else "high"
        )
        return common
    common.update(
        {
            "threshold": (
                settings.realtime_vad_threshold if settings is not None else 0.50
            ),
            "prefix_padding_ms": (
                settings.realtime_vad_prefix_padding_ms if settings is not None else 200
            ),
            "silence_duration_ms": (
                settings.realtime_vad_silence_duration_ms
                if settings is not None
                else 300
            ),
        }
    )
    return common


def build_realtime_session(
    context: VoiceContext,
    settings: GatewaySettings | None = None,
) -> dict[str, Any]:
    """Build a low-latency Realtime GA session for one bridge call."""
    external_tts = context.voice_provider != "openai"
    instructions = context.instructions
    if external_tts and context.first_message:
        instructions = (
            f"{instructions}\n\n# Estado de reproducción externo\n"
            f"El saludo inicial ya fue reproducido por el gateway: "
            f"{context.first_message!r}. No lo repitas ni vuelvas a presentarte. "
            "Continúa exactamente en el mismo idioma del saludo inicial y "
            "responde únicamente a lo que diga la persona usuaria. Si el "
            f"idioma configurado `{context.language}` no coincide con el saludo, "
            "prevalece el idioma del saludo. El locale de la voz TTS no "
            "determina el idioma de respuesta. Para reducir la espera, responde "
            "con una o dos frases cortas y formula una sola pregunta cada vez."
        )
    telephony_codec = context.telephony_codec.strip().casefold()
    if telephony_codec in {"pcma", "pcmu"}:
        input_format: dict[str, Any] = {"type": f"audio/{telephony_codec}"}
    else:
        input_format = {
            "type": "audio/pcm",
            "rate": OPENAI_INPUT_SAMPLE_RATE,
        }
    input_audio: dict[str, Any] = {
        "format": input_format,
        "turn_detection": _build_turn_detection(context, settings),
    }
    noise_reduction = (
        settings.realtime_noise_reduction if settings is not None else "near_field"
    )
    if noise_reduction != "off":
        input_audio["noise_reduction"] = {"type": noise_reduction}

    session: dict[str, Any] = {
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": ["text"] if external_tts else ["audio"],
        "audio": {"input": input_audio},
    }
    if _supports_reasoning_model(context.model):
        session["reasoning"] = {
            "effort": (
                settings.realtime_reasoning_effort if settings is not None else "low"
            )
        }
    tools = _sanitize_tools(context.tools)
    if tools:
        session["tools"] = tools
        session["tool_choice"] = "auto"
    if not external_tts:
        output_format: dict[str, Any]
        if telephony_codec in {"pcma", "pcmu"}:
            output_format = {"type": f"audio/{telephony_codec}"}
        else:
            output_format = {"type": "audio/pcm", "rate": OPENAI_INPUT_SAMPLE_RATE}
        session["audio"]["output"] = {
            "format": output_format,
            "voice": context.realtime_voice,
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
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._context = context
        self._call_id = call_id
        self._tool_executor = tool_executor
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
        self._response_create_pending = False
        self._continuation_after_tools = False
        self._response_lock = asyncio.Lock()
        self._handled_tool_call_ids: set[str] = set()
        self._last_speech_started_at: float | None = None
        self._last_speech_stopped_at: float | None = None
        self._turn_first_delta_logged = False
        self._turn_sequence = 0
        self._input_resampler = StatefulPcm16Resampler(
            SAMPLE_RATE, OPENAI_INPUT_SAMPLE_RATE
        )
        self._input_audio_buffer = bytearray()
        self._input_batch_bytes = int(
            OPENAI_INPUT_SAMPLE_RATE * 2 * settings.openai_input_batch_ms / 1000
        )
        self._g711_input_buffer = bytearray()
        self._g711_batch_bytes = int(
            SAMPLE_RATE * settings.openai_input_batch_ms / 1000
        )

    @property
    def last_speech_stopped_at(self) -> float | None:
        """Monotonic timestamp of the latest server VAD speech stop."""
        return self._last_speech_stopped_at

    @property
    def first_audio_latency_ms(self) -> float | None:
        """Return first audio latency in milliseconds."""
        if self._first_audio_started_at is None:
            return None
        return round((self._first_audio_started_at - self._started_at) * 1000, 2)

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
        session = build_realtime_session(self._context, self._settings)
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
                "language": self._context.language,
            },
        )

        greeting_item = build_external_greeting_item(self._context)
        if greeting_item is not None:
            await self._send(greeting_item)
            logger.info(
                "openai_external_greeting_recorded",
                extra={
                    "call_id": self._call_id,
                    "chars": len(self._context.first_message),
                    "language": self._context.language,
                },
            )

        if self._context.first_message and not external_tts:
            await self._send(
                {
                    "type": "response.create",
                    "response": {
                        "output_modalities": ["audio"],
                        "instructions": self._context.first_message,
                    },
                }
            )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("openai_bridge_started", extra={"call_id": self._call_id})

    async def send_g711(self, payload: bytes) -> None:
        """Append native PCMA/PCMU audio without an unnecessary resample."""
        if self._ws is None or self._closed.is_set() or not payload:
            return
        self._g711_input_buffer.extend(payload)
        self._input_audio_frames_sent += 1
        if len(self._g711_input_buffer) < self._g711_batch_bytes:
            return
        batch = bytes(self._g711_input_buffer)
        self._g711_input_buffer.clear()
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(batch).decode("ascii"),
            }
        )
        if self._input_audio_frames_sent <= 4 or self._input_audio_frames_sent % 50 == 0:
            logger.info(
                "openai_g711_input_audio_sent",
                extra={
                    "call_id": self._call_id,
                    "codec": self._context.telephony_codec,
                    "bytes": len(batch),
                    "frames_sent": self._input_audio_frames_sent,
                },
            )

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
        if should_log_audio:
            logger.info(
                "openai_input_audio_sent",
                extra={
                    "call_id": self._call_id,
                    "rate": OPENAI_INPUT_SAMPLE_RATE,
                    "bytes": len(batch),
                    "frames_sent": self._input_audio_frames_sent,
                },
            )

    async def cancel_response(self) -> bool:
        """Stop the active OpenAI response, avoiding invalid cancel requests."""
        if self._ws is None or self._closed.is_set() or not self._response_active:
            logger.debug(
                "openai_cancel_skipped_no_active_response",
                extra={"call_id": self._call_id},
            )
            return False
        await self._send({"type": "response.cancel"})
        logger.info(
            "openai_response_cancel_sent",
            extra={"call_id": self._call_id},
        )
        return True

    async def _request_response(self, *, reason: str) -> bool:
        """Create one response, deferring safely while another is active."""
        async with self._response_lock:
            if self._ws is None or self._closed.is_set():
                return False
            if self._response_active or self._response_create_pending:
                self._continuation_after_tools = True
                logger.info(
                    "openai_response_create_deferred",
                    extra={
                        "call_id": self._call_id,
                        "reason": reason,
                        "response_active": self._response_active,
                        "create_pending": self._response_create_pending,
                    },
                )
                return False
            self._response_create_pending = True
            await self._send(
                {
                    "event_id": f"evt_{uuid.uuid4().hex}",
                    "type": "response.create",
                    "response": {"output_modalities": ["text"]},
                }
            )
            logger.info(
                "openai_response_create_sent",
                extra={"call_id": self._call_id, "reason": reason},
            )
            return True

    async def close(self) -> None:
        """Close WebSocket and stop reader task."""
        self._closed.set()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        if self._ws is not None:
            if self._g711_input_buffer:
                await self._send(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(
                            bytes(self._g711_input_buffer)
                        ).decode("ascii"),
                    }
                )
                self._g711_input_buffer.clear()
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
        if event_type == "input_audio_buffer.speech_started":
            self._last_speech_started_at = time.perf_counter()
            self._turn_first_delta_logged = False
            self._turn_sequence += 1
            logger.info(
                "openai_speech_started",
                extra={"call_id": self._call_id, "turn": self._turn_sequence},
            )
            return
        if event_type == "input_audio_buffer.speech_stopped":
            self._last_speech_stopped_at = time.perf_counter()
            logger.info(
                "openai_speech_stopped",
                extra={"call_id": self._call_id, "turn": self._turn_sequence},
            )
            return
        if event_type == "response.created":
            self._response_create_pending = False
            self._response_active = True
            if self._last_speech_stopped_at is not None:
                logger.info(
                    "openai_vad_to_response_created_ms",
                    extra={
                        "call_id": self._call_id,
                        "turn": self._turn_sequence,
                        "latency_ms": round(
                            (time.perf_counter() - self._last_speech_stopped_at) * 1000,
                            2,
                        ),
                    },
                )
            return
        if event_type in {"response.cancelled", "response.failed"}:
            self._response_active = False
            self._response_create_pending = False
        if event_type == "error":
            raw_error = event.get("error")
            error = raw_error if isinstance(raw_error, dict) else {}
            code = str(error.get("code") or "")
            message = str(error.get("message") or "")
            if code == "response_cancel_not_active":
                self._response_active = False
                self._response_create_pending = False
                logger.warning(
                    "openai_cancel_not_active_ignored",
                    extra={"call_id": self._call_id},
                )
                return
            if code == "conversation_already_has_active_response":
                self._response_create_pending = False
                self._continuation_after_tools = True
                logger.warning(
                    "openai_active_response_conflict_ignored",
                    extra={"call_id": self._call_id},
                )
                return
            logger.error(
                "openai_error",
                extra={"call_id": self._call_id, "error": raw_error},
            )
            if "session.audio.input.format.rate" in message and "8000" in message:
                logger.error(
                    "openai_invalid_8000_rate_suppressed",
                    extra={"call_id": self._call_id},
                )
                await self.text_queue.put("__OPENAI_CONFIG_ERROR_SUPPRESSED__")
                return
            await self.text_queue.put("__OPENAI_ERROR__")
            return
        if event_type in {
            "response.output_audio.delta",
            "response.output_text.delta",
            "response.output_audio_transcript.delta",
        } and not self._turn_first_delta_logged:
            self._turn_first_delta_logged = True
            if self._last_speech_stopped_at is not None:
                logger.info(
                    "openai_turn_first_model_delta_ms",
                    extra={
                        "call_id": self._call_id,
                        "turn": self._turn_sequence,
                        "latency_ms": round(
                            (time.perf_counter() - self._last_speech_stopped_at) * 1000,
                            2,
                        ),
                        "event_type": event_type,
                    },
                )

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
                logger.info(
                    "openai_text_delta",
                    extra={"call_id": self._call_id, "chars": len(delta)},
                )
                await self.text_queue.put(delta)
            return
        if event_type == "response.done":
            self._response_active = False
            self._response_create_pending = False
            logger.info("openai_response_done", extra={"call_id": self._call_id})
            await self.text_queue.put("\n")
            if self._continuation_after_tools:
                self._continuation_after_tools = False
                await self._request_response(reason="tool_output")
            return
        if event_type in {
            "response.output_item.done",
            "response.function_call_arguments.done",
        }:
            await self._maybe_handle_tool_call(event)

    async def _maybe_handle_tool_call(self, event: dict[str, Any]) -> None:
        """Execute each function call once and continue only after response.done."""
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        if not isinstance(item, dict):
            return
        name = item.get("name")
        call_id = item.get("call_id") or item.get("id")
        arguments_raw = item.get("arguments") or item.get("arguments_json") or "{}"
        if not isinstance(name, str) or not name or not isinstance(call_id, str):
            return
        if call_id in self._handled_tool_call_ids:
            logger.info(
                "openai_tool_call_duplicate_ignored",
                extra={
                    "call_id": self._call_id,
                    "tool_call_id": call_id,
                    "tool_name": name,
                },
            )
            return
        self._handled_tool_call_ids.add(call_id)
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
            extra={
                "call_id": self._call_id,
                "tool_call_id": call_id,
                "tool_name": name,
            },
        )
        tool_started = time.perf_counter()
        output = await self._tool_executor(name, arguments)
        logger.info(
            "openai_tool_execution_ms",
            extra={
                "call_id": self._call_id,
                "tool_call_id": call_id,
                "tool_name": name,
                "latency_ms": round((time.perf_counter() - tool_started) * 1000, 2),
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
        self._continuation_after_tools = True
        logger.info(
            "openai_tool_output_submitted",
            extra={
                "call_id": self._call_id,
                "tool_call_id": call_id,
                "tool_name": name,
            },
        )
        if not self._response_active and not self._response_create_pending:
            self._continuation_after_tools = False
            await self._request_response(reason="tool_output")

