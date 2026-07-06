"""RTP packet helpers, jitter buffer, and port pool."""

from __future__ import annotations

import heapq
import random
import socket
import struct
from dataclasses import dataclass, field


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
    samples_per_packet: int = 160
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
        ready = [heapq.heappop(self._heap)[1] for _ in range(len(self._heap))]
        return ready


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
