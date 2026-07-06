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

from sip_gateway.backend import BackendClient, VoiceContext
from sip_gateway.config import GatewaySettings

logger = logging.getLogger(__name__)
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


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
        self.text_queue: asyncio.Queue[str] = asyncio.Queue()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._ws: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()
        self._first_audio_started_at: float | None = None

    @property
    def first_audio_latency_ms(self) -> float | None:
        """Return first audio latency in milliseconds."""
        if self._first_audio_started_at is None:
            return None
        return round((self._first_audio_started_at - self._started_at) * 1000, 2)

    async def start(self) -> None:
        """Open Realtime WebSocket and configure session."""
        self._started_at = time.perf_counter()
        url = f"{self._settings.openai_realtime_ws_url}?model={self._context.model}"
        headers = {
            "Authorization": (
                f"Bearer {self._settings.openai_api_key.get_secret_value()}"
            ),
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await connect(
            url,
            additional_headers=headers,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        )
        external_tts = self._context.voice_provider != "openai"
        session: dict[str, Any] = {
            "modalities": ["text"] if external_tts else ["text", "audio"],
            "instructions": self._context.instructions,
            "tools": self._context.tools,
            "tool_choice": "auto",
            "input_audio_format": "pcm16",
            "turn_detection": {
                "type": "server_vad",
                "interrupt_response": self._context.allow_interruptions,
            },
        }
        if not external_tts:
            session.update(
                {
                    "output_audio_format": "pcm16",
                    "voice": self._context.realtime_voice,
                }
            )
        await self._send(
            {
                "type": "session.update",
                "session": session,
            }
        )
        if self._context.first_message:
            await self._send(
                {
                    "type": "response.create",
                    "response": {"instructions": self._context.first_message},
                }
            )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("openai_bridge_started", extra={"call_id": self._call_id})

    async def send_pcm16(self, pcm16le: bytes) -> None:
        """Append one PCM16 audio frame to Realtime input."""
        if self._ws is None or self._closed.is_set():
            return
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm16le).decode("ascii"),
            }
        )

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
        async for raw_message in self._ws:
            try:
                event = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            await self._handle_event(event)

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "error":
            logger.error(
                "openai_realtime_error",
                extra={"call_id": self._call_id, "error": event.get("error")},
            )
            return
        if event_type in {"response.audio.delta", "response.output_audio.delta"}:
            delta = event.get("delta")
            if isinstance(delta, str):
                if self._first_audio_started_at is None:
                    self._first_audio_started_at = time.perf_counter()
                await self.audio_queue.put(base64.b64decode(delta))
            return
        if event_type in {
            "response.output_text.delta",
            "response.text.delta",
            "response.audio_transcript.delta",
        }:
            delta = event.get("delta")
            if isinstance(delta, str) and delta.strip():
                await self.text_queue.put(delta)
            return
        if event_type in {
            "response.output_item.done",
            "response.function_call_arguments.done",
        }:
            await self._maybe_handle_tool_call(event)

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
