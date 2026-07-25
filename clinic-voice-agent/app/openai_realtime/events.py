"""Realtime event parsing, persistence, transcripts, and tool execution."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CallEvent, CallOutcome, CallSession, CallStatus
from app.openai_realtime.tools import (
    ToolExecutionContext,
    execute_realtime_tool,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]
SendEvent = Callable[[dict[str, Any]], Awaitable[None]]

FUNCTION_CALL_EVENT = "response.done"
FUNCTION_CALL_ARGUMENTS_DONE_EVENT = "response.function_call_arguments.done"
USER_TRANSCRIPT_EVENT = "conversation.item.input_audio_transcription.completed"
ASSISTANT_TRANSCRIPT_EVENT = "response.output_audio_transcript.done"
ASSISTANT_TEXT_EVENT = "response.output_text.done"
TRANSCRIPT_EVENT_TYPES = frozenset(
    {
        USER_TRANSCRIPT_EVENT,
        ASSISTANT_TRANSCRIPT_EVENT,
        ASSISTANT_TEXT_EVENT,
        "conversation.item.input_audio_transcription.delta",
        "response.output_audio_transcript.delta",
        "response.output_text.delta",
    }
)
SUMMARY_TOOL_NAMES = frozenset({"transfer_to_human", "end_call"})


class SIPHeader(BaseModel):
    """One SIP header supplied in an incoming-call webhook."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=4096)


class RealtimeCallData(BaseModel):
    """Incoming SIP call identifiers and headers."""

    model_config = ConfigDict(extra="allow")

    call_id: str = Field(min_length=1, max_length=128)
    sip_headers: list[SIPHeader] = Field(default_factory=list, max_length=200)


class RealtimeIncomingCallEvent(BaseModel):
    """Official `realtime.call.incoming` webhook envelope."""

    model_config = ConfigDict(extra="allow")

    object: Literal["event"]
    id: str = Field(min_length=1, max_length=160)
    type: Literal["realtime.call.incoming"]
    created_at: int = Field(ge=0)
    data: RealtimeCallData


class UnknownRealtimeEvent(BaseModel):
    """Fallback webhook shape retained for safe acknowledgement."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    type: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FunctionCall:
    """Completed function call found in an official `response.done` event."""

    call_id: str
    name: str
    raw_arguments: str

    def parse_arguments(self) -> dict[str, Any]:
        """Decode the JSON argument string required by Realtime."""
        try:
            parsed = json.loads(self.raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Los argumentos de la herramienta no son JSON válido."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError("Los argumentos de la herramienta deben ser un objeto.")
        return parsed


def sip_headers_as_dict(headers: list[SIPHeader]) -> dict[str, str]:
    """Normalize SIP header names for case-insensitive lookup."""
    return {header.name.casefold(): header.value for header in headers}


def extract_sip_phone(value: str | None) -> str | None:
    """Extract a compact phone-like SIP or TEL user value."""
    if not value:
        return None
    match = re.search(r"(?:sip:|tel:)([^@;>]+)", value, flags=re.IGNORECASE)
    candidate = match.group(1) if match else value
    candidate = candidate.strip().strip('"<>')
    digits = "".join(character for character in candidate if character.isdigit())
    if not digits:
        return candidate[:32] or None
    return f"+{digits}" if "+" in candidate else digits


def function_calls_from_event(event: dict[str, Any]) -> tuple[FunctionCall, ...]:
    """Read completed calls from the SDK-defined Realtime server events."""
    event_type = event.get("type")
    if event_type == FUNCTION_CALL_ARGUMENTS_DONE_EVENT:
        call_id = event.get("call_id")
        name = event.get("name")
        arguments = event.get("arguments")
        if (
            isinstance(call_id, str)
            and isinstance(name, str)
            and isinstance(arguments, str)
        ):
            return (
                FunctionCall(
                    call_id=call_id,
                    name=name,
                    raw_arguments=arguments,
                ),
            )
        return ()
    if event_type != FUNCTION_CALL_EVENT:
        return ()
    response = event.get("response")
    if not isinstance(response, dict):
        return ()
    output = response.get("output")
    if not isinstance(output, list):
        return ()

    calls: list[FunctionCall] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        call_id = item.get("call_id")
        name = item.get("name")
        arguments = item.get("arguments")
        if (
            isinstance(call_id, str)
            and isinstance(name, str)
            and isinstance(arguments, str)
        ):
            calls.append(
                FunctionCall(
                    call_id=call_id,
                    name=name,
                    raw_arguments=arguments,
                )
            )
    return tuple(calls)


def function_output_event(
    function_call: FunctionCall,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Build the documented `function_call_output` conversation item."""
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": function_call.call_id,
            "output": json.dumps(output, ensure_ascii=False, default=str),
        },
    }


def _redact_tool_summary(arguments: str) -> str:
    """Remove model-generated free text that is not needed for operations."""
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    if not isinstance(parsed, dict) or "summary" not in parsed:
        return arguments
    parsed["summary"] = "[redacted]"
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def privacy_safe_event(
    event: dict[str, Any],
    *,
    transcription_enabled: bool,
) -> dict[str, Any]:
    """Redact transcripts and unnecessary tool summaries before storage."""
    event_type = str(event.get("type", "unknown"))
    if not transcription_enabled and event_type in TRANSCRIPT_EVENT_TYPES:
        return {
            "type": event_type,
            "event_id": event.get("event_id"),
            "item_id": event.get("item_id"),
            "response_id": event.get("response_id"),
            "transcript_redacted": True,
        }

    stored = copy.deepcopy(event)
    if (
        event_type == FUNCTION_CALL_ARGUMENTS_DONE_EVENT
        and stored.get("name") in SUMMARY_TOOL_NAMES
        and isinstance(stored.get("arguments"), str)
    ):
        stored["arguments"] = _redact_tool_summary(stored["arguments"])
        return stored

    if event_type != FUNCTION_CALL_EVENT:
        return stored
    response = stored.get("response")
    if not isinstance(response, dict):
        return stored
    output = response.get("output")
    if not isinstance(output, list):
        return stored
    for item in output:
        if (
            isinstance(item, dict)
            and item.get("type") == "function_call"
            and item.get("name") in SUMMARY_TOOL_NAMES
            and isinstance(item.get("arguments"), str)
        ):
            item["arguments"] = _redact_tool_summary(item["arguments"])
    return stored


class RealtimeEventProcessor:
    """Persist all events and execute completed model function calls."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        call_session_id: uuid.UUID,
        clinic_id: uuid.UUID,
        openai_call_id: str,
        transcription_enabled: bool | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._call_session_id = call_session_id
        self._clinic_id = clinic_id
        self._openai_call_id = openai_call_id
        self._transcription_enabled = (
            settings.enable_call_transcription
            if transcription_enabled is None
            else transcription_enabled
        )
        self._transcript_lines: list[str] = []
        self._processed_tool_call_ids = self._load_processed_tool_call_ids()
        self._server_event_count = 0
        self._client_event_count = 0
        self._last_error: str | None = None

    def _load_processed_tool_call_ids(self) -> set[str]:
        """Load persisted IDs so a reconnect does not repeat side effects."""
        with self._session_factory() as session:
            call_session = session.get(CallSession, self._call_session_id)
            if call_session is None:
                return set()
            values = call_session.conversation_state_json.get(
                "processed_tool_call_ids",
                [],
            )
            return {str(value) for value in values if value}

    def _persist_event(self, event: dict[str, Any], *, client: bool) -> None:
        """Store the full raw payload for later debugging."""
        event_type = str(event.get("type", "unknown"))
        stored_event = privacy_safe_event(
            event,
            transcription_enabled=self._transcription_enabled,
        )
        if client:
            event_type = f"client.{event_type}"
        with self._session_factory() as session:
            session.add(
                CallEvent(
                    call_session_id=self._call_session_id,
                    event_type=event_type,
                    payload_json=stored_event,
                )
            )
            session.commit()

    def _persist_runtime_state(self) -> None:
        """Save reconnect-safe counters and processed tool IDs."""
        with self._session_factory() as session:
            call_session = session.get(CallSession, self._call_session_id)
            if call_session is None:
                return
            state = dict(call_session.conversation_state_json)
            state.update(
                {
                    "processed_tool_call_ids": sorted(self._processed_tool_call_ids),
                    "server_event_count": self._server_event_count,
                    "client_event_count": self._client_event_count,
                }
            )
            if self._last_error:
                state["last_realtime_error"] = self._last_error
            call_session.conversation_state_json = state
            session.commit()

    def _set_active(self) -> None:
        """Mark the persisted call active after WebSocket connection."""
        with self._session_factory() as session:
            call_session = session.get(CallSession, self._call_session_id)
            if call_session is None:
                return
            call_session.status = CallStatus.ACTIVE
            session.commit()

    async def mark_active(self) -> None:
        """Move blocking SQLAlchemy work away from the event loop."""
        await asyncio.to_thread(self._set_active)

    def _capture_transcript(self, event: dict[str, Any]) -> None:
        """Collect documented completed transcript events."""
        if not self._transcription_enabled:
            return
        event_type = event.get("type")
        text: str | None = None
        role: str | None = None
        if event_type == USER_TRANSCRIPT_EVENT:
            text = event.get("transcript")
            role = "Paciente"
        elif event_type == ASSISTANT_TRANSCRIPT_EVENT:
            text = event.get("transcript")
            role = "Asistente"
        elif event_type == ASSISTANT_TEXT_EVENT:
            text = event.get("text")
            role = "Asistente"
        if isinstance(text, str) and text.strip() and role:
            self._transcript_lines.append(f"{role}: {text.strip()}")

    async def send_client_event(
        self,
        event: dict[str, Any],
        send_event: SendEvent,
    ) -> None:
        """Persist and send one client event over the control socket."""
        await asyncio.to_thread(self._persist_event, event, client=True)
        self._client_event_count += 1
        await send_event(event)

    async def _handle_function_call(
        self,
        function_call: FunctionCall,
        send_event: SendEvent,
    ) -> bool:
        """Execute one function once and return its output to the model."""
        if function_call.call_id in self._processed_tool_call_ids:
            logger.info(
                "realtime_tool_duplicate_skipped",
                extra={
                    "call_id": self._openai_call_id,
                    "tool_call_id": function_call.call_id,
                },
            )
            return False

        try:
            arguments = function_call.parse_arguments()
        except ValueError as exc:
            output = {
                "ok": False,
                "error": "invalid_tool_arguments",
                "message": str(exc),
            }
        else:
            context = ToolExecutionContext(
                settings=self._settings,
                session_factory=self._session_factory,
                call_session_id=self._call_session_id,
                clinic_id=self._clinic_id,
                openai_call_id=self._openai_call_id,
            )
            output = await asyncio.to_thread(
                execute_realtime_tool,
                function_call.name,
                arguments,
                context,
            )

        await self.send_client_event(
            function_output_event(function_call, output),
            send_event,
        )
        self._processed_tool_call_ids.add(function_call.call_id)
        await asyncio.to_thread(self._persist_runtime_state)
        logger.info(
            "realtime_tool_completed",
            extra={
                "call_id": self._openai_call_id,
                "tool_name": function_call.name,
                "tool_call_id": function_call.call_id,
                "ok": output.get("ok"),
            },
        )
        return True

    async def handle_event(
        self,
        event: dict[str, Any],
        send_event: SendEvent,
    ) -> None:
        """Store one server event and react to completed function calls."""
        await asyncio.to_thread(self._persist_event, event, client=False)
        self._server_event_count += 1
        self._capture_transcript(event)

        if event.get("type") == "error":
            error = event.get("error")
            self._last_error = (
                json.dumps(error, ensure_ascii=False, default=str)
                if isinstance(error, dict)
                else str(error or "Realtime error")
            )
            logger.error(
                "realtime_server_error",
                extra={
                    "call_id": self._openai_call_id,
                    "error": self._last_error,
                },
            )

        function_calls = function_calls_from_event(event)
        if not function_calls:
            return
        tool_output_sent = False
        for function_call in function_calls:
            tool_output_sent = (
                await self._handle_function_call(function_call, send_event)
                or tool_output_sent
            )
        if tool_output_sent:
            await self.send_client_event({"type": "response.create"}, send_event)

    def _finalize(
        self,
        *,
        status: CallStatus,
        summary: str | None,
    ) -> None:
        """Persist final transcript, summary, status, and timestamps."""
        with self._session_factory() as session:
            call_session = session.get(CallSession, self._call_session_id)
            if call_session is None:
                return
            transcript = "\n".join(self._transcript_lines).strip()
            if self._transcription_enabled and transcript:
                call_session.transcript_text = transcript
            call_session.summary_text = (
                summary
                or call_session.summary_text
                or (
                    "Llamada finalizada con error de control."
                    if status is CallStatus.FAILED
                    else "Llamada finalizada sin resumen del agente."
                )
            )
            call_session.status = status
            if call_session.outcome is None:
                call_session.outcome = (
                    CallOutcome.FAILED
                    if status is CallStatus.FAILED
                    else CallOutcome.NO_ACTION
                )
            call_session.ended_at = datetime.now(UTC)
            state = dict(call_session.conversation_state_json)
            state.update(
                {
                    "processed_tool_call_ids": sorted(self._processed_tool_call_ids),
                    "server_event_count": self._server_event_count,
                    "client_event_count": self._client_event_count,
                    "control_closed_at": datetime.now(UTC).isoformat(),
                }
            )
            if self._last_error:
                state["last_realtime_error"] = self._last_error
            call_session.conversation_state_json = state
            session.commit()

    async def finalize(
        self,
        *,
        status: CallStatus,
        summary: str | None = None,
    ) -> None:
        """Move final blocking persistence away from the event loop."""
        await asyncio.to_thread(self._finalize, status=status, summary=summary)
