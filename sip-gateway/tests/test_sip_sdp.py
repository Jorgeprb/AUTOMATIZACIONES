from __future__ import annotations

from sip_gateway.sdp import build_sdp_answer, parse_sdp_offer
from sip_gateway.sip import SipMessage, build_response, extract_sip_user

INVITE = (
    "INVITE sip:+34881170837@1.2.3.4 SIP/2.0\r\n"
    "Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-test\r\n"
    "From: <sip:+34600111222@voip.example>;tag=abc\r\n"
    "To: <sip:+34881170837@1.2.3.4>\r\n"
    "Call-ID: call-123\r\n"
    "CSeq: 1 INVITE\r\n"
    "Contact: <sip:+34600111222@10.0.0.1>\r\n"
    "Content-Type: application/sdp\r\n"
    "Content-Length: 126\r\n"
    "\r\n"
    "v=0\r\n"
    "o=- 1 1 IN IP4 10.0.0.1\r\n"
    "s=-\r\n"
    "c=IN IP4 10.0.0.1\r\n"
    "t=0 0\r\n"
    "m=audio 4000 RTP/AVP 8 0 101\r\n"
    "a=rtpmap:8 PCMA/8000\r\n"
)


def test_sip_parser_extracts_method_headers_and_numbers() -> None:
    message = SipMessage.parse(INVITE.encode())

    assert message.method == "INVITE"
    assert message.call_id == "call-123"
    assert message.branch == "z9hG4bK-test"
    assert message.caller == "+34600111222"
    assert message.callee == "+34881170837"
    assert extract_sip_user("<sip:bot@example.test>") == "bot"


def test_sip_response_preserves_transaction_headers() -> None:
    request = SipMessage.parse(INVITE.encode())
    response = build_response(request, 180, "Ringing", to_tag="server-tag")
    text = response.decode()

    assert text.startswith("SIP/2.0 180 Ringing")
    assert "Via: SIP/2.0/UDP 10.0.0.1:5060;branch=z9hG4bK-test" in text
    assert "Call-ID: call-123" in text
    assert "To: <sip:+34881170837@1.2.3.4>;tag=server-tag" in text


def test_sdp_offer_and_answer_support_pcmu_pcma() -> None:
    message = SipMessage.parse(INVITE.encode())
    offer = parse_sdp_offer(message.body)

    assert offer.connection_ip == "10.0.0.1"
    assert offer.audio_port == 4000
    assert offer.choose_payload() == 0

    answer = build_sdp_answer(
        ip="203.0.113.10",
        port=10000,
        payload_type=offer.choose_payload(),
        session_id=1234,
    )
    assert "m=audio 10000 RTP/AVP 0" in answer
    assert "a=rtpmap:0 PCMU/8000" in answer
