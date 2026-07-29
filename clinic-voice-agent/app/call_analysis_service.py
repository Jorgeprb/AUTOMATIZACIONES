"""Structured, non-sensitive post-call analysis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CallAnalysis, CallSession


class CallAnalysisPayload(BaseModel):
    sentiment_label: str = Field(pattern="^(positive|neutral|negative|mixed|unknown)$")
    sentiment_score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    intent: str | None = Field(default=None, max_length=120)
    resolved: bool | None = None
    resolution_label: str | None = Field(default=None, max_length=160)
    urgency: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    topics: list[str] = Field(default_factory=list, max_length=20)
    friction_points: list[str] = Field(default_factory=list, max_length=20)
    summary: str | None = Field(default=None, max_length=2000)


def analyze_call(session: Session, settings: Settings, call_session_id: uuid.UUID) -> CallAnalysis:
    call = session.get(CallSession, call_session_id)
    if call is None or call.clinic_id is None:
        raise ValueError("Call session not found.")
    row = session.scalar(
        select(CallAnalysis).where(CallAnalysis.call_session_id == call.id)
    )
    if row is None:
        row = CallAnalysis(call_session_id=call.id, clinic_id=call.clinic_id)
        session.add(row)
        session.flush()
    transcript = (call.transcript_text or "").strip()
    if not transcript:
        row.sentiment_label = "unknown"
        row.sentiment_score = Decimal("0")
        row.confidence = Decimal("0")
        row.summary = "No hay transcripción suficiente para analizar."
        row.error = None
        row.analyzed_at = datetime.now(UTC)
        row.model = settings.call_analysis_model
        return row

    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    response = client.responses.parse(
        model=settings.call_analysis_model,
        input=[
            {
                "role": "system",
                "content": (
                    "Analiza una llamada de atención al cliente exclusivamente para "
                    "estadística agregada y revisión humana. No infieras atributos "
                    "sensibles ni incluyas razonamientos internos. Devuelve solo la "
                    "estructura solicitada."
                ),
            },
            {"role": "user", "content": transcript[:30000]},
        ],
        text_format=CallAnalysisPayload,
    )
    payload = response.output_parsed
    if payload is None:
        raise RuntimeError("OpenAI returned no structured call analysis.")
    row.sentiment_label = payload.sentiment_label
    row.sentiment_score = Decimal(str(payload.sentiment_score))
    row.confidence = Decimal(str(payload.confidence))
    row.intent = payload.intent
    row.resolved = payload.resolved
    row.resolution_label = payload.resolution_label
    row.urgency = payload.urgency
    row.topics_json = payload.topics
    row.friction_points_json = payload.friction_points
    row.summary = payload.summary
    row.error = None
    row.analyzed_at = datetime.now(UTC)
    row.model = settings.call_analysis_model
    row.analysis_version = "v1"
    return row
