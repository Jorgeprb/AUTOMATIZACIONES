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

from sip_gateway.audio import (
    pcm16_24k_to_8k,
    sentence_chunks,
    tts_audio_to_g711_8k,
)
from sip_gateway.backend import BackendClient, VoiceContext
from sip_gateway.codecs import decode_g711, encode_g711, pcm16_energy
from sip_gateway.config import GatewaySettings
from sip_gateway.openai_bridge import OpenAIRealtimeBridge
from sip_gateway.rtp import (
    RTP_G711_PAYLOAD_BYTES,
    RTP_PACKET_INTERVAL_SEC,
    JitterBuffer,
    RtpIntervalStats,
    RTPPacket,
    RTPPortPool,
    RTPSequencer,
    comfort_silence_payload,
)
from sip_gateway.sdp import SdpOffer
from sip_gateway.sip import SipMessage

logger = logging.getLogger(__name__)

INITIAL_GREETING = "Ola, son a asistente virtual da clínica. En que podo axudarche?"
OPENAI_ERROR_MESSAGE = (
    "Desculpa, estou tendo un problema técnico co asistente. "
    "Podes chamar de novo nuns minutos."
)


def _looks_like_phone_number(value: str | None) -> bool:
    """Return whether a SIP user/header contains a usable phone number."""
    if not value:
        return False
    return re.search(r"\d{5,}", value) is not None


def select_called_number(invite: SipMessage, fallback_called_number: str | None) -> str:
    """Prefer real DID over route aliases such as sip:bot@..."""
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
    outbound_underruns: int = 0
    outbound_overruns: int = 0
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
        self.outbound_audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = asyncio.Event()
        self._bot_speaking = False
        self._stop_tts = asyncio.Event()
        self._rtp_sender_started = False
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
        if self.context is None:
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
        """Start RTP sender, initial greeting, OpenAI bridge and media tasks."""
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
        self._spawn(self._rtp_sender_loop())
        if context.voice_provider != "openai":
            self._spawn(self._speak_text(INITIAL_GREETING, reason="initial_greeting"))
        self._spawn(self._start_openai_bridge_and_media())
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
                "outbound_underruns": self.stats.outbound_underruns,
                "outbound_overruns": self.stats.outbound_overruns,
            },
        )

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _start_openai_bridge_and_media(self) -> None:
        assert self.bridge is not None and self.context is not None
        try:
            await self.bridge.start()
        except Exception:
            logger.exception(
                "openai_bridge_start_failed",
                extra={"call_id": self.call_id},
            )
            if self.context.voice_provider != "openai":
                await self._speak_text(
                    OPENAI_ERROR_MESSAGE,
                    reason="openai_start_failed",
                )
                return
            await self.close("openai_start_failed")
            return

        self._spawn(self._inbound_audio_loop())
        if self.context.voice_provider == "openai":
            self._spawn(self._openai_audio_output_loop())
        else:
            self._spawn(self._external_tts_output_loop())

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
            pcm16_8k = pcm16_24k_to_8k(pcm16)
            raw_g711 = encode_g711(self.payload_type, pcm16_8k)
            await self._queue_g711_audio(raw_g711, source="openai_audio")

    async def _external_tts_output_loop(self) -> None:
        assert self.bridge is not None and self.context is not None
        buffer = ""
        while not self._closed.is_set():
            try:
                delta = await asyncio.wait_for(
                    self.bridge.text_queue.get(),
                    timeout=0.45,
                )
            except TimeoutError:
                delta = ""
            if delta == "__OPENAI_ERROR__":
                await self._speak_text(OPENAI_ERROR_MESSAGE, reason="openai_error")
                continue
            if delta == "__OPENAI_CONFIG_ERROR_SUPPRESSED__":
                logger.error(
                    "openai_config_error_suppressed",
                    extra={"call_id": self.call_id},
                )
                continue
            buffer += delta
            if not buffer.strip():
                continue
            chunks = sentence_chunks(buffer)
            should_flush = not delta or delta == "\n"
            if not chunks and not should_flush:
                continue
            if not chunks and should_flush:
                chunks = [buffer.strip()]
            elif delta and buffer.strip() not in chunks[-1] and not should_flush:
                continue
            buffer = ""
            for chunk in chunks:
                if self._stop_tts.is_set():
                    self._stop_tts.clear()
                    break
                await self._speak_text(chunk, reason="assistant_response")

    async def _speak_text(self, text: str, *, reason: str) -> None:
        assert self.context is not None
        cleaned = text.strip()
        if not cleaned:
            return
        if self.context.voice_provider == "azure":
            logger.info(
                "azure_tts_started",
                extra={
                    "call_id": self.call_id,
                    "reason": reason,
                    "chars": len(cleaned),
                },
            )
        started = time.perf_counter()
        try:
            tts_audio = await self.backend.synthesize_tts(
                context=self.context,
                text=cleaned,
            )
            raw_g711 = tts_audio_to_g711_8k(
                tts_audio.audio,
                media_type=tts_audio.media_type,
                telephony_codec=self.context.telephony_codec,
                payload_type=self.payload_type,
            )
        except Exception:
            logger.exception(
                "tts_chunk_failed",
                extra={"call_id": self.call_id, "reason": reason},
            )
            return
        self.stats.tts_latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if self.context.voice_provider == "azure":
            logger.info(
                "azure_tts_first_chunk",
                extra={
                    "call_id": self.call_id,
                    "reason": reason,
                    "bytes": len(raw_g711),
                    "media_type": tts_audio.media_type,
                    "latency_ms": self.stats.tts_latency_ms,
                },
            )
        await self._queue_g711_audio(raw_g711, source=f"tts:{reason}")

    async def _queue_g711_audio(self, raw_g711: bytes, *, source: str) -> None:
        if not raw_g711:
            return
        buffered_ms = round(len(raw_g711) / 8.0, 2)
        logger.info(
            "tts_audio_bytes",
            extra={"call_id": self.call_id, "source": source, "bytes": len(raw_g711)},
        )
        logger.info(
            "tts_audio_buffered_ms",
            extra={
                "call_id": self.call_id,
                "source": source,
                "buffered_ms": buffered_ms,
            },
        )
        await self.outbound_audio_queue.put(raw_g711)

    async def _rtp_sender_loop(self) -> None:
        if self.rtp_transport is None:
            return
        initial_buffer_bytes = max(
            RTP_G711_PAYLOAD_BYTES,
            int(self.settings.rtp_initial_buffer_ms / 20) * RTP_G711_PAYLOAD_BYTES,
        )
        payload_buffer = bytearray()
        silence = comfort_silence_payload(self.payload_type)
        log_every = self.settings.rtp_packet_log_every
        interval_stats = RtpIntervalStats()
        last_send_at: float | None = None
        packet_index = 0
        underruns = 0
        overruns = 0
        first_packet_logged = False

        try:
            while not self._closed.is_set():
                while len(payload_buffer) < initial_buffer_bytes:
                    if self._closed.is_set():
                        return
                    try:
                        chunk = await asyncio.wait_for(
                            self.outbound_audio_queue.get(),
                            timeout=0.5 if payload_buffer else None,
                        )
                    except TimeoutError:
                        if payload_buffer:
                            break
                        continue
                    payload_buffer.extend(chunk)

                start = time.monotonic()
                packet_index = 0
                self._rtp_sender_started = True
                logger.info(
                    "rtp_sender_started",
                    extra={
                        "call_id": self.call_id,
                        "payload_type": self.payload_type,
                        "initial_buffer_bytes": len(payload_buffer),
                        "initial_buffer_ms": round(len(payload_buffer) / 8.0, 2),
                        "remote_rtp_addr": self.remote_rtp_addr,
                    },
                )

                while not self._closed.is_set():
                    target_send = start + packet_index * RTP_PACKET_INTERVAL_SEC
                    delay = target_send - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    else:
                        late_ms = -delay * 1000
                        if late_ms > 3:
                            overruns += 1
                            self.stats.outbound_overruns += 1
                            if overruns == 1 or overruns % log_every == 0:
                                logger.warning(
                                    "rtp_overrun",
                                    extra={
                                        "call_id": self.call_id,
                                        "late_ms": round(late_ms, 3),
                                        "overruns": overruns,
                                    },
                                )

                    if self._stop_tts.is_set():
                        payload_buffer.clear()
                        self._drain_outbound_audio_queue()
                        self._stop_tts.clear()

                    self._drain_outbound_audio_queue_into(payload_buffer)

                    if len(payload_buffer) >= RTP_G711_PAYLOAD_BYTES:
                        payload = bytes(payload_buffer[:RTP_G711_PAYLOAD_BYTES])
                        del payload_buffer[:RTP_G711_PAYLOAD_BYTES]
                        self._bot_speaking = True
                    else:
                        payload = silence
                        self._bot_speaking = False
                        underruns += 1
                        self.stats.outbound_underruns += 1
                        if underruns == 1 or underruns % log_every == 0:
                            logger.warning(
                                "rtp_underrun",
                                extra={
                                    "call_id": self.call_id,
                                    "underruns": underruns,
                                    "buffer_bytes": len(payload_buffer),
                                },
                            )

                    packet = self.sequencer.packet(payload).serialize()
                    self.rtp_transport.sendto(packet, self.remote_rtp_addr)
                    now = time.monotonic()
                    if last_send_at is not None:
                        interval_stats.add((now - last_send_at) * 1000)
                    last_send_at = now
                    self.stats.outbound_packets += 1

                    if not first_packet_logged:
                        first_packet_logged = True
                        logger.info(
                            "rtp_out_sent",
                            extra={
                                "call_id": self.call_id,
                                "payload_size": len(payload),
                                "payload_type": self.payload_type,
                                "sequence": self.sequencer.sequence_number - 1,
                            },
                        )

                    if self.stats.outbound_packets % log_every == 0:
                        snapshot = interval_stats.snapshot()
                        logger.info(
                            "rtp_out_packet_sent",
                            extra={
                                "call_id": self.call_id,
                                "rtp_out_packets_count": self.stats.outbound_packets,
                                "rtp_out_payload_size": len(payload),
                                "payload_type": self.payload_type,
                            },
                        )
                        logger.info(
                            "rtp_out_interval_ms",
                            extra={"call_id": self.call_id, **snapshot},
                        )
                        interval_stats.reset()

                    packet_index += 1
        finally:
            self._bot_speaking = False
            logger.info(
                "packetizer_finished",
                extra={
                    "call_id": self.call_id,
                    "rtp_out_packets_count": self.stats.outbound_packets,
                    "rtp_underruns": self.stats.outbound_underruns,
                    "rtp_overruns": self.stats.outbound_overruns,
                },
            )

    def _drain_outbound_audio_queue_into(self, payload_buffer: bytearray) -> None:
        while True:
            try:
                payload_buffer.extend(self.outbound_audio_queue.get_nowait())
            except asyncio.QueueEmpty:
                return

    def _drain_outbound_audio_queue(self) -> None:
        while True:
            try:
                self.outbound_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _max_duration_watchdog(self) -> None:
        await asyncio.sleep(self.settings.max_call_seconds)
        await self.close("max_duration")
