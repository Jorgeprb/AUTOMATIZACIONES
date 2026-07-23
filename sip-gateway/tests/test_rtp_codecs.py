from __future__ import annotations

import struct

from sip_gateway.audio import tts_audio_to_pcm16_8k
from sip_gateway.codecs import (
    decode_g711,
    encode_g711,
    pcm16_energy,
    pcm16le_to_pcma,
    pcm16le_to_pcmu,
    pcma_to_pcm16le,
    pcmu_to_pcm16le,
)
from sip_gateway.rtp import JitterBuffer, RTPPacket, RTPPortPool, RTPSequencer


def test_rtp_packet_roundtrip() -> None:
    packet = RTPPacket(
        payload_type=0,
        sequence_number=42,
        timestamp=160,
        ssrc=99,
        payload=b"abc",
        marker=True,
    )

    parsed = RTPPacket.parse(packet.serialize())

    assert parsed == packet


def test_rtp_sequencer_advances_sequence_and_timestamp() -> None:
    sequencer = RTPSequencer(payload_type=8, sequence_number=1, timestamp=100, ssrc=2)

    first = sequencer.packet(b"a")
    second = sequencer.packet(b"b")

    assert first.sequence_number == 1
    assert second.sequence_number == 2
    assert second.timestamp == 260


def test_jitter_buffer_orders_packets() -> None:
    buffer = JitterBuffer(depth=1)
    second = RTPPacket(0, 2, 320, 1, b"2")
    first = RTPPacket(0, 1, 160, 1, b"1")

    assert buffer.push(second) == []
    ready = buffer.push(first)

    assert [packet.sequence_number for packet in ready + buffer.flush()] == [1, 2]


def test_g711_codecs_decode_and_encode_audio() -> None:
    pcm = struct.pack("<hhhh", -1000, 0, 1000, 3000)

    pcmu = pcm16le_to_pcmu(pcm)
    pcma = pcm16le_to_pcma(pcm)

    assert len(pcmu) == 4
    assert len(pcma) == 4
    assert len(pcmu_to_pcm16le(pcmu)) == len(pcm)
    assert len(pcma_to_pcm16le(pcma)) == len(pcm)
    assert len(decode_g711(0, encode_g711(0, pcm))) == len(pcm)
    assert pcm16_energy(pcm) > 0


def test_tts_audio_to_pcm16_handles_raw_telephony_codecs() -> None:
    pcm = struct.pack("<hhhh", -1000, 0, 1000, 3000)

    assert tts_audio_to_pcm16_8k(
        pcm16le_to_pcma(pcm),
        media_type="audio/pcma",
        telephony_codec="pcma",
    )
    assert tts_audio_to_pcm16_8k(
        pcm16le_to_pcmu(pcm),
        media_type="audio/pcmu",
        telephony_codec="pcmu",
    )


def test_rtp_port_pool_leases_even_ports_and_releases() -> None:
    pool = RTPPortPool(10001, 10005)
    first = pool.lease()
    second = pool.lease()

    assert first == 10002
    assert second == 10004
    pool.release(first)
    assert pool.lease() == 10002


def test_rtp_parser_handles_extension_padding_and_sequence_wrap() -> None:
    import struct

    payload = b"voice"
    header = struct.pack("!BBHII", 0xB0, 8, 65535, 1234, 99)  # V2 + P + X
    extension = struct.pack("!HHI", 0xBEDE, 1, 0x01020304)
    padded = header + extension + payload + b"\x00\x00\x00\x04"
    parsed = RTPPacket.parse(padded)
    assert parsed.payload == payload

    buffer = JitterBuffer(depth=1)
    assert buffer.push(RTPPacket(8, 65535, 0, 99, b"a")) == []
    released = buffer.push(RTPPacket(8, 0, 160, 99, b"b"))
    assert [packet.sequence_number for packet in released] == [65535]
    assert [packet.sequence_number for packet in buffer.flush()] == [0]
