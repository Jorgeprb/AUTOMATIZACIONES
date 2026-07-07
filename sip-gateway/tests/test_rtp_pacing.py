from __future__ import annotations

from sip_gateway.rtp import RTP_PACKET_INTERVAL_SEC, absolute_rtp_schedule


def test_absolute_rtp_schedule_targets_20ms_without_drift() -> None:
    schedule = absolute_rtp_schedule(100.0, 100)
    intervals_ms = [
        (schedule[index] - schedule[index - 1]) * 1000
        for index in range(1, len(schedule))
    ]
    avg_ms = sum(intervals_ms) / len(intervals_ms)

    assert RTP_PACKET_INTERVAL_SEC == 0.02
    assert abs(avg_ms - 20.0) <= 3.0
    assert max(intervals_ms) < 23.0
    assert min(intervals_ms) > 17.0
