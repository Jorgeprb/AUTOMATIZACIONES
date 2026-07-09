"""RTP packet helpers, jitter buffer, packetizer, pacing, and port pool."""

from __future__ import annotations

import heapq
import random
import socket
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field

RTP_CLOCK_RATE = 8000
RTP_FRAME_MS = 20
RTP_PACKET_INTERVAL_SEC = RTP_FRAME_MS / 1000.0
RTP_SAMPLES_PER_PACKET = int(RTP_CLOCK_RATE * RTP_PACKET_INTERVAL_SEC)
RTP_G711_PAYLOAD_BYTES = RTP_SAMPLES_PER_PACKET
PAYLOAD_PCMU = 0
PAYLOAD_PCMA = 8
PCMU_SILENCE_BYTE = 0xFF
PCMA_SILENCE_BYTE = 0xD5


@dataclass(frozen=True, slots=True)
class RTPPacket:
    """Minimal RTP v2 packet."""

    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    payload: bytes
    marker: bool = False

    @classmethod
    def parse(cls, data: bytes) -> RTPPacket:
        """Parse one RTP packet without CSRC/extensions."""
        if len(data) < 12:
            raise ValueError("RTP packet too short")
        first, second, sequence, timestamp, ssrc = struct.unpack("!BBHII", data[:12])
        version = first >> 6
        if version != 2:
            raise ValueError("unsupported RTP version")
        csrc_count = first & 0x0F
        header_len = 12 + csrc_count * 4
        if len(data) < header_len:
            raise ValueError("RTP CSRC header truncated")
        return cls(
            payload_type=second & 0x7F,
            marker=bool(second & 0x80),
            sequence_number=sequence,
            timestamp=timestamp,
            ssrc=ssrc,
            payload=data[header_len:],
        )

    def serialize(self) -> bytes:
        """Serialize one RTP packet."""
        second = self.payload_type & 0x7F
        if self.marker:
            second |= 0x80
        header = struct.pack(
            "!BBHII",
            0x80,
            second,
            self.sequence_number & 0xFFFF,
            self.timestamp & 0xFFFFFFFF,
            self.ssrc & 0xFFFFFFFF,
        )
        return header + self.payload


@dataclass(slots=True)
class RTPSequencer:
    """Generate sequence/timestamp values for 8 kHz telephony RTP."""

    payload_type: int
    samples_per_packet: int = RTP_SAMPLES_PER_PACKET
    sequence_number: int = field(default_factory=lambda: random.randint(0, 65535))
    timestamp: int = field(default_factory=lambda: random.randint(0, 2**32 - 1))
    ssrc: int = field(default_factory=lambda: random.randint(1, 2**32 - 1))

    def packet(self, payload: bytes, *, marker: bool = False) -> RTPPacket:
        """Build next RTP packet and advance sequence/timestamp."""
        packet = RTPPacket(
            payload_type=self.payload_type,
            sequence_number=self.sequence_number,
            timestamp=self.timestamp,
            ssrc=self.ssrc,
            payload=payload,
            marker=marker,
        )
        self.sequence_number = (self.sequence_number + 1) & 0xFFFF
        self.timestamp = (self.timestamp + self.samples_per_packet) & 0xFFFFFFFF
        return packet


def comfort_silence_byte(payload_type: int) -> int:
    """Return the conventional G.711 silence byte for the selected codec."""
    if payload_type == PAYLOAD_PCMA:
        return PCMA_SILENCE_BYTE
    if payload_type == PAYLOAD_PCMU:
        return PCMU_SILENCE_BYTE
    raise ValueError(f"unsupported payload type: {payload_type}")


def comfort_silence_payload(payload_type: int) -> bytes:
    """Return one 20 ms G.711 silence payload."""
    return bytes([comfort_silence_byte(payload_type)]) * RTP_G711_PAYLOAD_BYTES


def iter_g711_20ms_frames(
    audio: bytes,
    *,
    pad_byte: int,
    frame_size: int = RTP_G711_PAYLOAD_BYTES,
) -> Iterator[bytes]:
    """Yield 20 ms G.711 payload frames, padding only the final frame."""
    if not audio:
        return
    for offset in range(0, len(audio), frame_size):
        frame = audio[offset : offset + frame_size]
        if len(frame) < frame_size:
            frame += bytes([pad_byte]) * (frame_size - len(frame))
        yield frame


def build_g711_rtp_packets(
    audio: bytes,
    *,
    sequencer: RTPSequencer,
    pad_byte: int | None = None,
) -> list[RTPPacket]:
    """Packetize raw PCMA/PCMU 8 kHz mono audio into 20 ms RTP packets."""
    if pad_byte is None:
        pad_byte = comfort_silence_byte(sequencer.payload_type)
    return [
        sequencer.packet(frame)
        for frame in iter_g711_20ms_frames(audio, pad_byte=pad_byte)
    ]


def absolute_rtp_schedule(
    start: float,
    packet_count: int,
    *,
    interval: float = RTP_PACKET_INTERVAL_SEC,
) -> list[float]:
    """Return absolute send deadlines for a fixed-rate RTP stream."""
    if packet_count < 0:
        raise ValueError("packet_count must be >= 0")
    return [start + index * interval for index in range(packet_count)]


@dataclass(slots=True)
class RtpIntervalStats:
    """Compact interval statistics for periodic RTP pacing logs."""

    count: int = 0
    min_ms: float | None = None
    max_ms: float | None = None
    total_ms: float = 0.0

    def add(self, interval_ms: float) -> None:
        """Add one observed inter-packet interval."""
        self.count += 1
        self.total_ms += interval_ms
        self.min_ms = (
            interval_ms if self.min_ms is None else min(self.min_ms, interval_ms)
        )
        self.max_ms = (
            interval_ms if self.max_ms is None else max(self.max_ms, interval_ms)
        )

    def snapshot(self) -> dict[str, float | int | None]:
        """Return rounded stats and reset-friendly values."""
        avg = self.total_ms / self.count if self.count else None
        return {
            "count": self.count,
            "min_ms": round(self.min_ms, 3) if self.min_ms is not None else None,
            "max_ms": round(self.max_ms, 3) if self.max_ms is not None else None,
            "avg_ms": round(avg, 3) if avg is not None else None,
        }

    def reset(self) -> None:
        """Clear collected interval stats."""
        self.count = 0
        self.min_ms = None
        self.max_ms = None
        self.total_ms = 0.0


class JitterBuffer:
    """Tiny packet-ordering jitter buffer keyed by RTP sequence number."""

    def __init__(self, depth: int = 4) -> None:
        self.depth = depth
        self._heap: list[tuple[int, RTPPacket]] = []

    def push(self, packet: RTPPacket) -> list[RTPPacket]:
        """Push a packet and return packets ready for playout."""
        heapq.heappush(self._heap, (packet.sequence_number, packet))
        ready: list[RTPPacket] = []
        while len(self._heap) > self.depth:
            ready.append(heapq.heappop(self._heap)[1])
        return ready

    def flush(self) -> list[RTPPacket]:
        """Return all buffered packets ordered by sequence."""
        return [heapq.heappop(self._heap)[1] for _ in range(len(self._heap))]


class RTPPortPool:
    """Allocate even UDP RTP ports from a configured range."""

    def __init__(self, port_min: int, port_max: int) -> None:
        if port_min > port_max:
            raise ValueError("RTP_PORT_MIN must be <= RTP_PORT_MAX")
        self._available = list(range(port_min + (port_min % 2), port_max + 1, 2))
        self._leased: set[int] = set()

    def lease(self) -> int:
        """Lease one RTP port."""
        if not self._available:
            raise RuntimeError("no RTP ports available")
        port = self._available.pop(0)
        self._leased.add(port)
        return port

    def release(self, port: int) -> None:
        """Release one RTP port back to the pool."""
        if port not in self._leased:
            return
        self._leased.remove(port)
        self._available.append(port)
        self._available.sort()

    @property
    def available_count(self) -> int:
        """Return how many RTP ports remain available."""
        return len(self._available)

    @staticmethod
    def bind_udp(host: str, port: int) -> socket.socket:
        """Create a non-blocking UDP socket bound to a port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.bind((host, port))
        return sock
