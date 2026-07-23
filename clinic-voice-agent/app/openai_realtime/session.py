"""OpenAI Realtime SIP acceptance and WebSocket call control."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedOK

from app.config import Settings
from app.db import get_session_factory
from app.models import CallStatus
from app.openai_realtime.events import RealtimeEventProcessor
from app.openai_realtime.prompt_builder import (
    ClinicContext,
    build_realtime_instructions,
)
from app.openai_realtime.tools import get_realtime_tools
from app.prompts import build_receptionist_instructions

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
OPENAI_REALTIME_BASE_URL = "https://api.openai.com/v1/realtime"
OPENAI_REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"
CONTROL_RECONNECT_ATTEMPTS = 2
CONTROL_RECONNECT_DELAY_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class RealtimeSessionConfig:
    """Configuration sent to the SIP call accept endpoint."""

    model: str
    voice: str
    instructions: str
    transcription_enabled: bool
    language: str = "es"
    initial_message: str | None = None
    fallback_voice: str | None = None
    allow_interruptions: bool = True
    idle_timeout_ms: int | None = None
    vad_mode: str = "server_vad"
    vad_threshold: float = 0.50
    vad_prefix_padding_ms: int = 200
    vad_silence_duration_ms: int = 300
    vad_eagerness: str = "high"
    noise_reduction: str = "near_field"
    reasoning_effort: str = "low"
    transcription_delay: str = "minimal"

    def as_accept_payload(self) -> dict[str, Any]:
        """Serialize a low-latency documented Realtime session payload."""
        turn_detection: dict[str, Any] = {
            "type": self.vad_mode,
            "create_response": True,
            "interrupt_response": self.allow_interruptions,
        }
        if self.vad_mode == "semantic_vad":
            turn_detection["eagerness"] = self.vad_eagerness
        else:
            turn_detection.update(
                {
                    "threshold": self.vad_threshold,
                    "prefix_padding_ms": self.vad_prefix_padding_ms,
                    "silence_duration_ms": self.vad_silence_duration_ms,
                }
            )
            if self.idle_timeout_ms is not None:
                turn_detection["idle_timeout_ms"] = self.idle_timeout_ms

        input_audio: dict[str, Any] = {"turn_detection": turn_detection}
        if self.noise_reduction != "off":
            input_audio["noise_reduction"] = {"type": self.noise_reduction}
        if self.transcription_enabled:
            input_audio["transcription"] = {
                "model": "gpt-realtime-whisper",
                "language": self.language.split("-", maxsplit=1)[0],
                "delay": self.transcription_delay,
            }

        payload: dict[str, Any] = {
            "type": "realtime",
            "model": self.model,
            "audio": {
                "input": input_audio,
                "output": {"voice": self.voice},
            },
            "instructions": self.instructions,
            "tools": list(get_realtime_tools()),
            "tool_choice": "auto",
        }
        if self.model.strip().casefold().startswith("gpt-realtime-2"):
            payload["reasoning"] = {"effort": self.reasoning_effort}
        return payload


def build_session_config(
    settings: Settings,
    *,
    clinic_id: uuid.UUID | None = None,
    call_session_id: uuid.UUID | None = None,
    caller_phone: str | None = None,
    context: ClinicContext | None = None,
) -> RealtimeSessionConfig:
    """Create a session configuration with trusted per-call identifiers."""
    instructions = (
        build_realtime_instructions(context)
        if context is not None
        else build_receptionist_instructions(settings)
    )
    effective_clinic_id = context.clinic.id if context is not None else clinic_id
    context_lines: list[str] = []
    if effective_clinic_id is not None:
        context_lines.append(
            f"clinic_id técnico de esta llamada: {effective_clinic_id}. "
            "Úsalo en las herramientas y no lo leas en voz alta."
        )
    if call_session_id is not None:
        context_lines.append(
            f"call_session_id técnico de esta llamada: {call_session_id}. "
            "Úsalo al crear citas y no lo leas en voz alta."
        )
    if caller_phone:
        context_lines.append(
            f"Caller ID recibido: {caller_phone}. Confírmalo si hay duda."
        )
    if context_lines:
        instructions = f"{instructions}\n\n# Contexto técnico\n" + "\n".join(
            context_lines
        )
    return RealtimeSessionConfig(
        model=(
            context.active_assistant_config.realtime_model
            if context is not None
            else settings.openai_realtime_model
        ),
        voice=(
            context.active_assistant_config.realtime_voice
            if context is not None
            else settings.openai_realtime_voice
        ),
        instructions=instructions,
        transcription_enabled=(
            context.active_assistant_config.transcript_enabled
            if context is not None
            else settings.enable_call_transcription
        ),
        language=(
            context.active_assistant_config.language if context is not None else "es"
        ),
        initial_message=(
            context.active_assistant_config.first_message
            if context is not None
            else None
        ),
        fallback_voice=(
            context.active_assistant_config.fallback_voice
            if context is not None
            else None
        ),
        allow_interruptions=(
            context.active_assistant_config.allow_interruptions
            if context is not None
            else True
        ),
        idle_timeout_ms=(
            context.active_assistant_config.idle_timeout_ms
            if context is not None
            else None
        ),
        vad_mode=settings.openai_realtime_vad_mode,
        vad_threshold=settings.openai_realtime_vad_threshold,
        vad_prefix_padding_ms=settings.openai_realtime_vad_prefix_padding_ms,
        vad_silence_duration_ms=settings.openai_realtime_vad_silence_duration_ms,
        vad_eagerness=settings.openai_realtime_vad_eagerness,
        noise_reduction=settings.openai_realtime_noise_reduction,
        reasoning_effort=settings.openai_realtime_reasoning_effort,
        transcription_delay=settings.openai_realtime_transcription_delay,
    )


def initial_greeting_event(
    settings: Settings,
    *,
    initial_message: str | None = None,
) -> dict[str, Any]:
    """Ask the existing SIP session to produce its first spoken response."""
    instructions = initial_message or (
        f"Saluda brevemente en español. Di que eres el asistente virtual "
        f"de {settings.clinic_name} y pregunta en qué puedes ayudar."
    )
    return {
        "type": "response.create",
        "response": {"instructions": instructions},
    }


def _authorization_headers(settings: Settings) -> dict[str, str]:
    """Build OpenAI bearer headers without logging the API key."""
    return {
        "Authorization": (f"Bearer {settings.openai_api_key.get_secret_value()}"),
        "Content-Type": "application/json",
    }


async def accept_realtime_call(
    settings: Settings,
    *,
    call_id: str,
    payload: dict[str, Any],
) -> None:
    """Accept and configure one incoming SIP call."""
    url = f"{OPENAI_REALTIME_BASE_URL}/calls/{call_id}/accept"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            url,
            headers=_authorization_headers(settings),
            json=payload,
        )
        response.raise_for_status()


async def hangup_realtime_call(settings: Settings, *, call_id: str) -> None:
    """Request teardown of an active Realtime call."""
    url = f"{OPENAI_REALTIME_BASE_URL}/calls/{call_id}/hangup"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            headers=_authorization_headers(settings),
        )
        response.raise_for_status()


class RealtimeCallController:
    """Control an accepted SIP call over its existing Realtime WebSocket."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        call_session_id: uuid.UUID,
        clinic_id: uuid.UUID,
        openai_call_id: str,
        initial_message: str | None = None,
        transcription_enabled: bool | None = None,
    ) -> None:
        self._settings = settings
        self._openai_call_id = openai_call_id
        self._greeting_sent = False
        self._initial_message = initial_message
        self._processor = RealtimeEventProcessor(
            settings=settings,
            session_factory=session_factory,
            call_session_id=call_session_id,
            clinic_id=clinic_id,
            openai_call_id=openai_call_id,
            transcription_enabled=transcription_enabled,
        )

    async def _run_once(self) -> None:
        """Run one WebSocket connection attempt."""
        url = f"{OPENAI_REALTIME_WS_URL}?call_id={self._openai_call_id}"
        headers = {
            "Authorization": (
                f"Bearer {self._settings.openai_api_key.get_secret_value()}"
            )
        }
        async with connect(
            url,
            additional_headers=headers,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as websocket:
            logger.info(
                "realtime_control_connected",
                extra={"call_id": self._openai_call_id},
            )
            await self._processor.mark_active()

            async def send_event(event: dict[str, Any]) -> None:
                await websocket.send(json.dumps(event, ensure_ascii=False, default=str))

            if not self._greeting_sent:
                await self._processor.send_client_event(
                    initial_greeting_event(
                        self._settings,
                        initial_message=self._initial_message,
                    ),
                    send_event,
                )
                self._greeting_sent = True

            async for raw_message in websocket:
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8", errors="replace")
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError:
                    event = {
                        "type": "invalid_json",
                        "raw": raw_message,
                    }
                if not isinstance(event, dict):
                    event = {
                        "type": "invalid_json_shape",
                        "raw": event,
                    }
                await self._processor.handle_event(event, send_event)

    async def run(self) -> None:
        """Run control with one reconnect attempt and clean finalization."""
        for attempt in range(CONTROL_RECONNECT_ATTEMPTS):
            try:
                await self._run_once()
                await self._processor.finalize(status=CallStatus.COMPLETED)
                logger.info(
                    "realtime_control_closed",
                    extra={"call_id": self._openai_call_id},
                )
                return
            except ConnectionClosedOK:
                await self._processor.finalize(status=CallStatus.COMPLETED)
                logger.info(
                    "realtime_call_completed",
                    extra={"call_id": self._openai_call_id},
                )
                return
            except asyncio.CancelledError:
                await self._processor.finalize(
                    status=CallStatus.FAILED,
                    summary="Control de llamada detenido durante el cierre de la app.",
                )
                raise
            except Exception as exc:
                logger.warning(
                    "realtime_control_attempt_failed",
                    extra={
                        "call_id": self._openai_call_id,
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )
                if attempt + 1 < CONTROL_RECONNECT_ATTEMPTS:
                    await asyncio.sleep(CONTROL_RECONNECT_DELAY_SECONDS)
                    continue
                await self._processor.finalize(
                    status=CallStatus.FAILED,
                    summary="Falló la conexión de control Realtime.",
                )
                logger.exception(
                    "realtime_control_failed",
                    extra={"call_id": self._openai_call_id},
                )


_active_control_tasks: set[asyncio.Task[None]] = set()


def start_call_control_task(
    *,
    settings: Settings,
    call_session_id: uuid.UUID,
    clinic_id: uuid.UUID,
    openai_call_id: str,
    session_factory: SessionFactory | None = None,
    initial_message: str | None = None,
    transcription_enabled: bool | None = None,
) -> asyncio.Task[None]:
    """Start and retain one background controller task."""
    controller = RealtimeCallController(
        settings=settings,
        session_factory=session_factory or get_session_factory(),
        call_session_id=call_session_id,
        clinic_id=clinic_id,
        openai_call_id=openai_call_id,
        initial_message=initial_message,
        transcription_enabled=transcription_enabled,
    )
    task = asyncio.create_task(
        controller.run(),
        name=f"realtime-call-{openai_call_id}",
    )
    _active_control_tasks.add(task)
    task.add_done_callback(_active_control_tasks.discard)
    return task


async def shutdown_call_control_tasks() -> None:
    """Cancel active call controllers during application shutdown."""
    tasks = list(_active_control_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _active_control_tasks.clear()
