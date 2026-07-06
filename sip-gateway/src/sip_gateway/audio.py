"""Audio helpers for telephony bridge output."""

from __future__ import annotations

import audioop
import io
import wave

SAMPLE_RATE = 8000
SAMPLES_PER_20MS = 160
BYTES_PER_20MS_PCM16 = SAMPLES_PER_20MS * 2


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


def chunk_pcm16_20ms(pcm16le: bytes) -> list[bytes]:
    """Split PCM16 into 20 ms telephony frames, padding the last frame."""
    chunks: list[bytes] = []
    for offset in range(0, len(pcm16le), BYTES_PER_20MS_PCM16):
        chunk = pcm16le[offset : offset + BYTES_PER_20MS_PCM16]
        if len(chunk) < BYTES_PER_20MS_PCM16:
            chunk += b"\x00" * (BYTES_PER_20MS_PCM16 - len(chunk))
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
