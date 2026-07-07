"""OpenAI Realtime GA WebSocket bridge for server-to-server media."""

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
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from sip_gateway.backend import BackendClient, VoiceContext
from sip_gateway.config import GatewaySettings
from sip_gateway.sdp import PAYLOAD_PCMA, PAYLOAD_PCMU

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def realtime_audio_format_for_payload(payload_type: int) -> dict[str, str]:
    """Return GA Realtime audio format object for static telephony payload."""
    if payload_type == PAYLOAD_PCMA:
        return {"type": "audio/pcma"}
    if payload_type == PAYLOAD_PCMU:
        return {"type": "audio/pcmu"}
    raise ValueError(f"unsupported telephony RTP payload type: {payload_type}")


class OpenAIRealtimeBridge:
    """Bidirectional audio/text bridge to OpenAI Realtime GA."""

    def __init__(
        self,
        *,
        settings: GatewaySettings,
        backend: BackendClient,
        context: VoiceContext,
        call_id: str,
        tool_executor: ToolExecutor,
        payload_type: int,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._context = context
        self._call_id = call_id
        self._tool_executor = tool_executor
        self._payload_type = payload_type
        self.text_queue: asyncio.Queue[str] = asyncio.Queue()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._ws: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()
        self._first_audio_started_at: float | None = None
        self._started_at = 0.0

    @property
    def first_audio_latency_ms(self) -> float | None:
        """Return first audio latency in milliseconds."""
        if self._first_audio_started_at is None:
            return None
        return round((self._first_audio_started_at - self._started_at) * 1000, 2)

    @property
    def output_audio_is_telephony(self) -> bool:
        """Return whether audio_queue chunks are already G.711 RTP payload bytes."""
        return self._context.voice_provider == "openai"

    async def start(self) -> None:
        """Open Realtime WebSocket and configure a GA session."""
        self._started_at = time.perf_counter()
        model = self._settings.openai_realtime_model or self._context.model
        url = self._build_realtime_url(model)
        headers = {
            "Authorization": (
                f"Bearer {self._settings.openai_api_key.get_secret_value()}"
            )
        }
        logger.info(
            "openai_ws_connecting",
            extra={"call_id": self._call_id, "model": model, "url": url},
        )
        self._ws = await connect(
            url,
            additional_headers=headers,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        )
        logger.info(
            "openai_ws_connected",
            extra={"call_id": self._call_id, "model": model},
        )

        await self._send(
            {
                "type": "session.update",
                "session": self._build_ga_session(),
            }
        )
        logger.info(
            "openai_session_update_sent",
            extra={
                "call_id": self._call_id,
                "voice_provider": self._context.voice_provider,
                "output_modalities": [
                    "text" if self._uses_external_tts else "audio"
                ],
            },
        )

        if self._context.first_message and not self._uses_external_tts:
            await self._send(
                {
                    "type": "response.create",
                    "response": {
                        "instructions": self._context.first_message,
                        "output_modalities": ["audio"],
                    },
                }
            )

        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("openai_bridge_started", extra={"call_id": self._call_id})

    @property
    def _uses_external_tts(self) -> bool:
        return self._context.voice_provider != "openai"

    def _build_realtime_url(self, model: str) -> str:
        base_url = self._settings.openai_realtime_ws_url
        if "?" in base_url:
            return base_url
        return f"{base_url}?{urlencode({'model': model})}"

    def _build_ga_session(self) -> dict[str, Any]:
        input_audio = {
            "format": realtime_audio_format_for_payload(self._payload_type),
            "turn_detection": {
                "type": "server_vad",
                "create_response": True,
                "interrupt_response": self._context.allow_interruptions,
            },
        }
        if self._context.idle_timeout_ms is not None:
            input_audio["turn_detection"]["idle_timeout_ms"] = (
                self._context.idle_timeout_ms
            )

        session: dict[str, Any] = {
            "type": "realtime",
            "instructions": self._context.instructions,
            "audio": {"input": input_audio},
            "output_modalities": ["text" if self._uses_external_tts else "audio"],
        }

        if self._context.tools:
            session["tools"] = self._context.tools
            session["tool_choice"] = "auto"

        if not self._uses_external_tts:
            session["audio"]["output"] = {
                "format": realtime_audio_format_for_payload(self._payload_type),
                "voice": self._context.realtime_voice,
            }

        return session

    async def send_audio(self, audio_payload: bytes) -> None:
        """Append one G.711 audio frame to Realtime input."""
        if self._ws is None or self._closed.is_set():
            return
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_payload).decode("ascii"),
            }
        )

    async def send_pcm16(self, pcm16le: bytes) -> None:
        """Backward-compatible alias; prefer send_audio with GA G.711 input."""
        await self.send_audio(pcm16le)

    async def cancel_response(self) -> None:
        """Ask OpenAI to stop current response for barge-in."""
        if self._ws is None or self._closed.is_set():
            return
        await self._send({"type": "response.cancel"})

    async def close(self) -> None:
        """Close WebSocket and stop reader task."""
        self._closed.set()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        if self._ws is not None:
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
        except ConnectionClosed as exc:
            await self._handle_transport_error(exc)
        except Exception as exc:
            await self._handle_transport_error(exc)

    async def _handle_transport_error(self, exc: BaseException) -> None:
        logger.exception(
            "openai_error",
            extra={
                "call_id": self._call_id,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            },
        )
        await self._fallback_text_to_avoid_silence()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")

        if event_type in {"session.created", "session.updated"}:
            logger.info(
                "openai_session_created",
                extra={"call_id": self._call_id, "event_type": event_type},
            )
            return

        if event_type == "error":
            logger.error(
                "openai_error",
                extra={"call_id": self._call_id, "error": event.get("error")},
            )
            await self._fallback_text_to_avoid_silence()
            return

        if event_type == "response.output_audio.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                if self._first_audio_started_at is None:
                    self._first_audio_started_at = time.perf_counter()
                await self.audio_queue.put(base64.b64decode(delta))
            return

        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                logger.info(
                    "openai_text_delta",
                    extra={"call_id": self._call_id, "chars": len(delta)},
                )
                await self.text_queue.put(delta)
            return

        if event_type == "response.output_audio_transcript.delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                logger.info(
                    "openai_text_delta",
                    extra={
                        "call_id": self._call_id,
                        "chars": len(delta),
                        "source": "audio_transcript",
                    },
                )
            return

        if event_type == "response.done":
            response = event.get("response") if isinstance(event.get("response"), dict) else {}
            logger.info(
                "openai_response_done",
                extra={
                    "call_id": self._call_id,
                    "status": response.get("status") if response else None,
                },
            )
            return

        if event_type in {
            "response.output_item.done",
            "response.function_call_arguments.done",
        }:
            await self._maybe_handle_tool_call(event)

    async def _fallback_text_to_avoid_silence(self) -> None:
        self._closed.set()
        if self._uses_external_tts:
            await self.text_queue.put(self._settings.openai_failure_message)

    async def _maybe_handle_tool_call(self, event: dict[str, Any]) -> None:
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        if not isinstance(item, dict):
            return
        name = item.get("name")
        call_id = item.get("call_id") or item.get("id") or str(uuid.uuid4())
        arguments_raw = item.get("arguments") or item.get("arguments_json") or "{}"
        if not isinstance(name, str) or not name:
            return
        try:
            arguments = (
                json.loads(arguments_raw)
                if isinstance(arguments_raw, str)
                else dict(arguments_raw)
            )
        except (TypeError, ValueError):
            arguments = {}
        output = await self._tool_executor(name, arguments)
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
        await self._send({"type": "response.create"})
