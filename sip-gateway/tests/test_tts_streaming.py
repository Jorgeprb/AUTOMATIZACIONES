from __future__ import annotations

from sip_gateway.session import split_tts_stream


def test_tts_stream_keeps_incomplete_delta_buffered() -> None:
    chunks, remainder = split_tts_stream("Boas, en que podo")
    assert chunks == []
    assert remainder == "Boas, en que podo"


def test_tts_stream_emits_complete_sentence_and_keeps_tail() -> None:
    chunks, remainder = split_tts_stream("Boas. En que podo")
    assert chunks == ["Boas."]
    assert remainder.strip() == "En que podo"


def test_tts_stream_force_flushes_final_response_once() -> None:
    chunks, remainder = split_tts_stream("En que podo axudarche", force=True)
    assert chunks == ["En que podo axudarche"]
    assert remainder == ""
