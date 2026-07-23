#!/usr/bin/env python3
"""Summarize JSON latency events from sip-gateway/api Docker logs."""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict

EVENT_FIELDS = {
    "openai_vad_to_response_created_ms": "latency_ms",
    "openai_turn_first_model_delta_ms": "latency_ms",
    "turn_speech_stop_to_audio_queued_ms": "latency_ms",
    "openai_tool_execution_ms": "latency_ms",
    "realtime_vad_to_response_created_ms": "latency_ms",
    "realtime_turn_first_delta_ms": "latency_ms",
    "realtime_tool_execution_ms": "latency_ms",
    "azure_tts_first_chunk": "latency_ms",
}


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * q))
    return ordered[index]


def main() -> int:
    samples: dict[str, list[float]] = defaultdict(list)
    for raw in sys.stdin:
        start = raw.find("{")
        if start < 0:
            continue
        try:
            event = json.loads(raw[start:])
        except json.JSONDecodeError:
            continue
        name = str(event.get("message") or event.get("event") or "")
        field = EVENT_FIELDS.get(name)
        if not field:
            continue
        value = event.get(field)
        if isinstance(value, (int, float)):
            samples[name].append(float(value))

    if not samples:
        print("No se encontraron métricas de latencia compatibles.")
        return 1

    print(f"{'métrica':42} {'n':>5} {'media':>10} {'p50':>10} {'p95':>10} {'máx':>10}")
    for name in sorted(samples):
        values = samples[name]
        print(
            f"{name:42} {len(values):5d} "
            f"{statistics.fmean(values):10.1f} "
            f"{percentile(values, 0.50):10.1f} "
            f"{percentile(values, 0.95):10.1f} "
            f"{max(values):10.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
