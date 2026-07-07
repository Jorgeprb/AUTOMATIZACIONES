"""Minimal SDP parsing/building for PCMU/PCMA RTP audio."""

from __future__ import annotations

from dataclasses import dataclass

PAYLOAD_PCMU = 0
PAYLOAD_PCMA = 8
SUPPORTED_PAYLOADS = {PAYLOAD_PCMU: "PCMU", PAYLOAD_PCMA: "PCMA"}


@dataclass(frozen=True, slots=True)
class SdpOffer:
    """Parsed RTP media offer."""

    connection_ip: str
    audio_port: int
    payloads: list[int]

    def choose_payload(self) -> int:
        """Choose preferred supported payload."""
        if PAYLOAD_PCMU in self.payloads:
            return PAYLOAD_PCMU
        if PAYLOAD_PCMA in self.payloads:
            return PAYLOAD_PCMA
        raise ValueError("SDP offer does not include PCMU/8000 or PCMA/8000")


def parse_sdp_offer(body: str) -> SdpOffer:
    """Parse enough SDP to answer an audio call."""
    connection_ip = ""
    audio_port = 0
    payloads: list[int] = []
    rtpmap: dict[int, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("c="):
            parts = line.split()
            if parts:
                connection_ip = parts[-1]
        elif line.startswith("m=audio"):
            parts = line.split()
            if len(parts) >= 4:
                audio_port = int(parts[1])
                payloads = [int(item) for item in parts[3:] if item.isdigit()]
        elif line.startswith("a=rtpmap:"):
            left, _, codec = line.partition(" ")
            payload = left.split(":", maxsplit=1)[1]
            if payload.isdigit():
                rtpmap[int(payload)] = codec.upper()
    supported = [
        payload
        for payload in payloads
        if payload in SUPPORTED_PAYLOADS
        and (
            payload not in rtpmap
            or rtpmap[payload].startswith(f"{SUPPORTED_PAYLOADS[payload]}/8000")
        )
    ]
    if not connection_ip or audio_port <= 0:
        raise ValueError("SDP offer missing connection IP or audio port")
    if not supported:
        raise ValueError("SDP offer does not include supported G.711 payloads")
    return SdpOffer(
        connection_ip=connection_ip,
        audio_port=audio_port,
        payloads=supported,
    )


def build_sdp_answer(
    *,
    ip: str,
    port: int,
    payload_type: int,
    session_id: int,
) -> str:
    """Build a minimal SDP answer for one chosen G.711 payload."""
    codec = SUPPORTED_PAYLOADS[payload_type]
    return "\r\n".join(
        [
            "v=0",
            f"o=clinic-voice-agent {session_id} {session_id} IN IP4 {ip}",
            "s=Clinic Voice Agent",
            f"c=IN IP4 {ip}",
            "t=0 0",
            f"m=audio {port} RTP/AVP {payload_type}",
            f"a=rtpmap:{payload_type} {codec}/8000",
            "a=sendrecv",
            "",
        ]
    )
