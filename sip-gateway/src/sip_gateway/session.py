"""Per-call SIP/RTP lifecycle and media pipeline."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Coroutine
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sip_gateway.audio import chunk_pcm16_20ms, sentence_chunks, tts_audio_to_pcm16_8k
from sip_gateway.backend import BackendClient, VoiceContext
from sip_gateway.codecs import decode_g711, encode_g711, pcm16_energy
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import OpenAIRealtimeBridge
from sip_gateway.rtp import JitterBuffer, RTPPacket, RTPPortPool, RTPSequencer
from sip_gateway.sdp import SdpOffer
from sip_gateway.sip import SipMessage

logger = logging.getLogger(__name__)


def _looks_like_phone_number(value: str | None) -> bool:
    """Return whether a SIP user/header contains a usable phone number."""
    if not value:
        return False
    return re.search(r"\d{5,}", value) is not None


def select_called_number(invite: SipMessage, fallback_called_number: str | None) -> str:
    """Prefer real DID over route aliases such as sip:bot@... ."""
    sip_callee = invite.callee
    if fallback_called_number and not _looks_like_phone_number(sip_callee):
        return fallback_called_number
    return sip_callee or fallback_called_number or ""


class RtpProtocol(asyncio.DatagramProtocol):
    """Forward RTP datagrams into a call session."""

    def __init__(self, call: GatewayCallSession) -> None:
        self._call = call

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Queue inbound RTP packet."""
        self._call.on_rtp(data, addr)


@dataclass(slots=True)
class CallStats:
    """Runtime metrics logged at teardown."""

    inbound_packets: int = 0
    outbound_packets: int = 0
    first_audio_latency_ms: float | None = None
    tts_latency_ms: float | None = None


class GatewayCallSession:
    """One bridged call between SIP/RTP and OpenAI/TTS."""

    def __init__(
        self,
        *,
        settings: GatewaySettings,
        backend: BackendClient,
        port_pool: RTPPortPool,
        invite: SipMessage,
        sip_addr: tuple[str, int],
        offer: SdpOffer,
        payload_type: int,
        rtp_port: int,
    ) -> None:
        self.settings = settings
        self.backend = backend
        self.port_pool = port_pool
        self.invite = invite
        self.sip_addr = sip_addr
        self.offer = offer
        self.payload_type = payload_type
        self.rtp_port = rtp_port
        self.call_id = invite.call_id or str(uuid.uuid4())
        self.local_tag = uuid.uuid4().hex[:12]
        self.openai_call_id = f"vps-{self.call_id}"
        self.remote_rtp_addr = (offer.connection_ip, offer.audio_port)
        self.context: VoiceContext | None = None
        self.rtp_transport: asyncio.DatagramTransport | None = None
        self.bridge: OpenAIRealtimeBridge | None = None
        self.jitter = JitterBuffer(depth=3)
        self.sequencer = RTPSequencer(payload_type=payload_type)
        self.inbound_queue: asyncio.Queue[RTPPacket] = asyncio.Queue(maxsize=200)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = asyncio.Event()
        self._bot_speaking = False
        self._stop_tts = asyncio.Event()
        self.stats = CallStats()
        self.started_at = time.perf_counter()

    async def prepare(self) -> None:
        """Bind RTP and resolve backend context before answering INVITE."""
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: RtpProtocol(self),
            local_addr=(self.settings.sip_bind_host, self.rtp_port),
        )
        self.rtp_transport = transport  # type: ignore[assignment]
        called_number = select_called_number(
            self.invite,
            self.settings.fallback_called_number,
        )
        self.context = await self.backend.resolve_voice_context(
            called_number=called_number,
            caller_phone=self.invite.caller,
            caller=self.invite.caller,
            callee=self.invite.callee,
            sip_to=self.invite.header("to") or self.invite.header("t"),
            sip_from=self.invite.header("from") or self.invite.header("f"),
            openai_call_id=self.openai_call_id,
            provider_call_id=self.call_id,
        )
        logger.info(
            "sip_call_prepared",
            extra={
                "call_id": self.call_id,
                "clinic_id": self.context.clinic_id,
                "caller": self.invite.caller,
                "callee": called_number,
                "provider": self.context.voice_provider,
                "codec": "PCMU" if self.payload_type == 0 else "PCMA",
            },
        )

    async def start_media(self) -> None:
        """Start OpenAI bridge and media tasks after ACK."""
        if self.context is None:
            raise RuntimeError("call context not prepared")
        context = self.context

        async def tool_executor(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return await self.backend.execute_tool(
                clinic_id=context.clinic_id,
                call_session_id=context.call_session_id,
                openai_call_id=self.openai_call_id,
                name=name,
                arguments=arguments,
            )

        self.bridge = OpenAIRealtimeBridge(
            settings=self.settings,
            backend=self.backend,
            context=context,
            call_id=self.call_id,
            tool_executor=tool_executor,
        )
        await self.bridge.start()
        self._spawn(self._inbound_audio_loop())
        if context.voice_provider == "openai":
            self._spawn(self._openai_audio_output_loop())
        else:
            self._spawn(self._external_tts_output_loop())
        self._spawn(self._max_duration_watchdog())

    def on_rtp(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process one RTP datagram from UDP protocol."""
        try:
            packet = RTPPacket.parse(data)
        except ValueError:
            return
        self.remote_rtp_addr = addr
        for ready in self.jitter.push(packet):
            try:
                self.inbound_queue.put_nowait(ready)
            except asyncio.QueueFull:
                _ = self.inbound_queue.get_nowait()
                self.inbound_queue.put_nowait(ready)

    async def close(self, reason: str = "normal") -> None:
        """Close bridge, cancel tasks, close RTP, and release port."""
        if self._closed.is_set():
            return
        self._closed.set()
        current_task = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current_task:
                task.cancel()
        for task in list(self._tasks):
            if task is current_task:
                continue
            with suppress(asyncio.CancelledError):
                await task
        if self.bridge is not None:
            await self.bridge.close()
            self.stats.first_audio_latency_ms = self.bridge.first_audio_latency_ms
        if self.rtp_transport is not None:
            self.rtp_transport.close()
        self.port_pool.release(self.rtp_port)
        logger.info(
            "sip_call_closed",
            extra={
                "call_id": self.call_id,
                "clinic_id": self.context.clinic_id if self.context else None,
                "reason": reason,
                "caller": self.invite.caller,
                "callee": self.invite.callee,
                "provider": self.context.voice_provider if self.context else None,
                "codec": "PCMU" if self.payload_type == 0 else "PCMA",
                "latency_first_audio": self.stats.first_audio_latency_ms,
                "tts_latency": self.stats.tts_latency_ms,
                "inbound_packets": self.stats.inbound_packets,
                "outbound_packets": self.stats.outbound_packets,
            },
        )

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _inbound_audio_loop(self) -> None:
        assert self.bridge is not None
        while not self._closed.is_set():
            packet = await self.inbound_queue.get()
            if packet.payload_type != self.payload_type:
                continue
            self.stats.inbound_packets += 1
            pcm16 = decode_g711(packet.payload_type, packet.payload)
            energy = pcm16_energy(pcm16)
            if self._bot_speaking and energy >= self.settings.silence_energy_threshold:
                self._stop_tts.set()
                await self.bridge.cancel_response()
                logger.info("barge_in_detected", extra={"call_id": self.call_id})
            await self.bridge.send_pcm16(pcm16)

    async def _openai_audio_output_loop(self) -> None:
        assert self.bridge is not None
        while not self._closed.is_set():
            pcm16 = await self.bridge.audio_queue.get()
            await self._send_pcm16_as_rtp(pcm16)

    async def _external_tts_output_loop(self) -> None:
        assert self.bridge is not None and self.context is not None
        buffer = ""
        while not self._closed.is_set():
            try:
                delta = await asyncio.wait_for(
                    self.bridge.text_queue.get(),
                    timeout=0.4,
                )
            except TimeoutError:
                delta = ""
            buffer += delta
            chunks = sentence_chunks(buffer)
            if not chunks:
                continue
            if delta and buffer.strip() not in chunks[-1]:
                continue
            buffer = ""
            for chunk in chunks:
                if self._stop_tts.is_set():
                    self._stop_tts.clear()
                    break
                started = time.perf_counter()
                try:
                    tts_audio = await self.backend.synthesize_tts(
                        context=self.context,
                        text=chunk,
                    )
                    pcm16 = tts_audio_to_pcm16_8k(
                        tts_audio.audio,
                        media_type=tts_audio.media_type,
                        telephony_codec=self.context.telephony_codec,
                    )
                except Exception:
                    logger.exception(
                        "tts_chunk_failed",
                        extra={"call_id": self.call_id},
                    )
                    continue
                self.stats.tts_latency_ms = round(
                    (time.perf_counter() - started) * 1000,
                    2,
                )
                await self._send_pcm16_as_rtp(pcm16)

    async def _send_pcm16_as_rtp(self, pcm16: bytes) -> None:
        if self.rtp_transport is None:
            return
        self._bot_speaking = True
        try:
            for frame in chunk_pcm16_20ms(pcm16):
                if self._closed.is_set() or self._stop_tts.is_set():
                    self._stop_tts.clear()
                    break
                payload = encode_g711(self.payload_type, frame)
                packet = self.sequencer.packet(payload).serialize()
                self.rtp_transport.sendto(packet, self.remote_rtp_addr)
                self.stats.outbound_packets += 1
                await asyncio.sleep(0.02)
        finally:
            self._bot_speaking = False

    async def _max_duration_watchdog(self) -> None:
        await asyncio.sleep(self.settings.max_call_seconds)
        await self.close("max_duration")
