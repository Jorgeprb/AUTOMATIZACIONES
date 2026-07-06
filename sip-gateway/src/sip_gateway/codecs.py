"""G.711 PCMU/PCMA conversion helpers."""

from __future__ import annotations

import struct

BIAS = 0x84
CLIP = 32635


def _pcm16_samples(data: bytes) -> list[int]:
    if len(data) % 2:
        data = data[:-1]
    return list(struct.unpack("<" + "h" * (len(data) // 2), data))


def _pack_pcm16(samples: list[int]) -> bytes:
    clipped = [max(-32768, min(32767, int(sample))) for sample in samples]
    return struct.pack("<" + "h" * len(clipped), *clipped)


def ulaw_to_linear(value: int) -> int:
    """Decode one µ-law byte to signed PCM16."""
    value = (~value) & 0xFF
    t = ((value & 0x0F) << 3) + BIAS
    t <<= (value & 0x70) >> 4
    return BIAS - t if value & 0x80 else t - BIAS


def linear_to_ulaw(sample: int) -> int:
    """Encode one PCM16 sample to µ-law."""
    sample = max(-CLIP, min(CLIP, sample))
    mask = 0xFF
    if sample < 0:
        sample = BIAS - sample
        mask = 0x7F
    else:
        sample += BIAS
    segment = 7
    for exponent in range(7):
        if sample <= (0x1F << (exponent + 3)):
            segment = exponent
            break
    mantissa = (sample >> (segment + 3)) & 0x0F
    return (~((segment << 4) | mantissa) & mask) & 0xFF


def alaw_to_linear(value: int) -> int:
    """Decode one A-law byte to signed PCM16."""
    value ^= 0x55
    t = (value & 0x0F) << 4
    segment = (value & 0x70) >> 4
    if segment == 0:
        t += 8
    elif segment == 1:
        t += 0x108
    else:
        t += 0x108
        t <<= segment - 1
    return t if value & 0x80 else -t


_ALAW_DECODE_TABLE = [alaw_to_linear(i) for i in range(256)]


def linear_to_alaw(sample: int) -> int:
    """Encode one PCM16 sample to A-law using nearest decoded level."""
    return min(
        range(256),
        key=lambda candidate: abs(_ALAW_DECODE_TABLE[candidate] - sample),
    )


def pcmu_to_pcm16le(data: bytes) -> bytes:
    """Decode PCMU payload to PCM16 little-endian."""
    return _pack_pcm16([ulaw_to_linear(byte) for byte in data])


def pcm16le_to_pcmu(data: bytes) -> bytes:
    """Encode PCM16 little-endian to PCMU."""
    return bytes(linear_to_ulaw(sample) for sample in _pcm16_samples(data))


def pcma_to_pcm16le(data: bytes) -> bytes:
    """Decode PCMA payload to PCM16 little-endian."""
    return _pack_pcm16([alaw_to_linear(byte) for byte in data])


def pcm16le_to_pcma(data: bytes) -> bytes:
    """Encode PCM16 little-endian to PCMA."""
    return bytes(linear_to_alaw(sample) for sample in _pcm16_samples(data))


def decode_g711(payload_type: int, payload: bytes) -> bytes:
    """Decode RTP G.711 payload to PCM16."""
    if payload_type == 0:
        return pcmu_to_pcm16le(payload)
    if payload_type == 8:
        return pcma_to_pcm16le(payload)
    raise ValueError(f"unsupported payload type: {payload_type}")


def encode_g711(payload_type: int, pcm16le: bytes) -> bytes:
    """Encode PCM16 to RTP G.711 payload."""
    if payload_type == 0:
        return pcm16le_to_pcmu(pcm16le)
    if payload_type == 8:
        return pcm16le_to_pcma(pcm16le)
    raise ValueError(f"unsupported payload type: {payload_type}")


def pcm16_energy(pcm16le: bytes) -> int:
    """Return average absolute amplitude for speech/silence detection."""
    samples = _pcm16_samples(pcm16le)
    if not samples:
        return 0
    return int(sum(abs(sample) for sample in samples) / len(samples))
