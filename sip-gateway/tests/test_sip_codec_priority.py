from __future__ import annotations

from sip_gateway.config import GatewaySettings
from sip_gateway.sdp import PAYLOAD_PCMA, PAYLOAD_PCMU, build_sdp_answer, parse_sdp_offer


def test_telephony_codec_pcma_has_priority_when_offered() -> None:
    settings = GatewaySettings(openai_api_key="test-key", telephony_codec="pcma")
    offer = parse_sdp_offer(
        "\r\n".join(
            [
                "v=0",
                "o=- 1 1 IN IP4 10.0.0.1",
                "s=-",
                "c=IN IP4 10.0.0.1",
                "t=0 0",
                "m=audio 4000 RTP/AVP 0 8 101",
                "a=rtpmap:0 PCMU/8000",
                "a=rtpmap:8 PCMA/8000",
            ]
        )
    )

    assert offer.choose_payload(settings.telephony_codec) == PAYLOAD_PCMA
    answer = build_sdp_answer(
        ip="203.0.113.10",
        port=10002,
        payload_type=offer.choose_payload(settings.telephony_codec),
        session_id=1234,
    )
    assert "m=audio 10002 RTP/AVP 8" in answer
    assert "a=rtpmap:8 PCMA/8000" in answer


def test_telephony_codec_falls_back_if_preferred_not_offered() -> None:
    settings = GatewaySettings(openai_api_key="test-key", telephony_codec="pcma")
    offer = parse_sdp_offer(
        "\r\n".join(
            [
                "v=0",
                "o=- 1 1 IN IP4 10.0.0.1",
                "s=-",
                "c=IN IP4 10.0.0.1",
                "t=0 0",
                "m=audio 4000 RTP/AVP 0",
                "a=rtpmap:0 PCMU/8000",
            ]
        )
    )

    assert offer.choose_payload(settings.telephony_codec) == PAYLOAD_PCMU
