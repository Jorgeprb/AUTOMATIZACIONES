"""Audio helpers for telephony bridge input and output."""

from __future__ import annotations

import audioop
import io
import wave

from sip_gateway.codecs import (
    encode_g711,
    pcma_to_pcm16le,
    pcmu_to_pcm16le,
)
from sip_gateway.rtp import (
    PAYLOAD_PCMA,
    PAYLOAD_PCMU,
    RTP_G711_PAYLOAD_BYTES,
    RTP_SAMPLES_PER_PACKET,
    comfort_silence_byte,
)

SAMPLE_RATE = 8000
OPENAI_INPUT_SAMPLE_RATE = 24000
SAMPLES_PER_20MS = RTP_SAMPLES_PER_PACKET
BYTES_PER_20MS_PCM16 = SAMPLES_PER_20MS * 2
G711_BYTES_PER_20MS = RTP_G711_PAYLOAD_BYTES


class StatefulPcm16Resampler:
    """Stateful mono PCM16 resampler avoiding discontinuities between RTP frames."""

    def __init__(self, source_rate: int, target_rate: int) -> None:
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._state: object | None = None

    def convert(self, data: bytes) -> bytes:
        if self.source_rate == self.target_rate:
            return data
        converted, self._state = audioop.ratecv(
            data, 2, 1, self.source_rate, self.target_rate, self._state
        )
        return converted


def wav_to_pcm16_8k(data: bytes) -> bytes:
    """Decode WAV PCM to mono 8 kHz PCM16 little-endian."""
    with wave.open(io.BytesIO(data), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
    if channels > 1:
        frames = audioop.tomono(frames, 2, 0.5, 0.5)
    if frame_rate != SAMPLE_RATE:
        frames, _ = audioop.ratecv(frames, 2, 1, frame_rate, SAMPLE_RATE, None)
    return frames


def resample_pcm16_mono(
    data: bytes,
    *,
    source_rate: int,
    target_rate: int,
) -> bytes:
    """Resample mono PCM16 little-endian audio."""
    if source_rate == target_rate:
        return data
    converted, _ = audioop.ratecv(data, 2, 1, source_rate, target_rate, None)
    return converted


def pcm16_8k_to_24k(data: bytes) -> bytes:
    """Convert telephony PCM16/8 kHz to OpenAI Realtime PCM16/24 kHz."""
    return resample_pcm16_mono(
        data,
        source_rate=SAMPLE_RATE,
        target_rate=OPENAI_INPUT_SAMPLE_RATE,
    )


def pcm16_24k_to_8k(data: bytes) -> bytes:
    """Convert OpenAI Realtime PCM16/24 kHz output to telephony PCM16/8 kHz."""
    return resample_pcm16_mono(
        data,
        source_rate=OPENAI_INPUT_SAMPLE_RATE,
        target_rate=SAMPLE_RATE,
    )


def tts_audio_to_pcm16_8k(
    data: bytes,
    *,
    media_type: str,
    telephony_codec: str,
) -> bytes:
    """Convert backend TTS audio to 8 kHz PCM16."""
    normalized = media_type.casefold()
    codec = telephony_codec.casefold()
    if normalized in {"audio/pcma", "audio/x-alaw"}:
        return pcma_to_pcm16le(data)
    if normalized in {"audio/pcmu", "audio/basic", "audio/x-mulaw"}:
        return pcmu_to_pcm16le(data)
    if normalized in {"audio/l16", "audio/pcm", "audio/pcm16"}:
        return data
    if codec == "pcma" and normalized == "application/octet-stream":
        return pcma_to_pcm16le(data)
    if codec == "pcmu" and normalized == "application/octet-stream":
        return pcmu_to_pcm16le(data)
    return wav_to_pcm16_8k(data)


def tts_audio_to_g711_8k(
    data: bytes,
    *,
    media_type: str,
    telephony_codec: str,
    payload_type: int,
) -> bytes:
    """Convert backend TTS audio directly to raw PCMA/PCMU payload bytes."""
    normalized = media_type.casefold()
    codec = telephony_codec.casefold()
    if payload_type == PAYLOAD_PCMA and normalized in {
        "audio/pcma",
        "audio/x-alaw",
        "application/octet-stream",
    } and codec == "pcma":
        return data
    if payload_type == PAYLOAD_PCMU and normalized in {
        "audio/pcmu",
        "audio/basic",
        "audio/x-mulaw",
        "application/octet-stream",
    } and codec == "pcmu":
        return data
    pcm16 = tts_audio_to_pcm16_8k(
        data,
        media_type=media_type,
        telephony_codec=telephony_codec,
    )
    return encode_g711(payload_type, pcm16)


def chunk_pcm16_20ms(pcm16le: bytes) -> list[bytes]:
    """Split PCM16 into 20 ms telephony frames, padding the last frame."""
    chunks: list[bytes] = []
    for offset in range(0, len(pcm16le), BYTES_PER_20MS_PCM16):
        chunk = pcm16le[offset : offset + BYTES_PER_20MS_PCM16]
        if len(chunk) < BYTES_PER_20MS_PCM16:
            chunk += b"\x00" * (BYTES_PER_20MS_PCM16 - len(chunk))
        chunks.append(chunk)
    return chunks


def chunk_g711_20ms(
    audio: bytes,
    *,
    payload_type: int,
) -> list[bytes]:
    """Split raw G.711 into 20 ms payloads, padding final frame with silence."""
    pad = bytes([comfort_silence_byte(payload_type)])
    chunks: list[bytes] = []
    for offset in range(0, len(audio), G711_BYTES_PER_20MS):
        chunk = audio[offset : offset + G711_BYTES_PER_20MS]
        if len(chunk) < G711_BYTES_PER_20MS:
            chunk += pad * (G711_BYTES_PER_20MS - len(chunk))
        chunks.append(chunk)
    return chunks


def sentence_chunks(text: str, *, max_chars: int = 240) -> list[str]:
    """Chunk assistant text on punctuation for lower TTS latency."""
    chunks: list[str] = []
    current = ""
    for char in text.strip():
        current += char
        if char in ".?!;:\n" or len(current) >= max_chars:
            cleaned = current.strip()
            if cleaned:
                chunks.append(cleaned)
            current = ""
    cleaned = current.strip()
    if cleaned:
        chunks.append(cleaned)
    return chunks
