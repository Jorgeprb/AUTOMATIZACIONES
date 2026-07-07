from __future__ import annotations

from sip_gateway.rtp import (
    RTP_G711_PAYLOAD_BYTES,
    RTPSequencer,
    build_g711_rtp_packets,
)


def test_one_second_pcma_packetizes_to_50_rtp_packets() -> None:
    raw_pcma = bytes([0xD5]) * 8000
    sequencer = RTPSequencer(
        payload_type=8,
        sequence_number=1000,
        timestamp=0,
        ssrc=123456,
    )

    packets = build_g711_rtp_packets(raw_pcma, sequencer=sequencer)

    assert len(packets) == 50
    for index, packet in enumerate(packets):
        assert len(packet.payload) == RTP_G711_PAYLOAD_BYTES
        assert packet.payload_type == 8
        assert packet.timestamp == index * 160
        assert packet.sequence_number == 1000 + index
        assert packet.ssrc == 123456
