"""Verified OpenAI Realtime incoming-call webhook."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import InvalidWebhookSignatureError, OpenAI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import CallEvent, CallSession, CallStatus
from app.openai_realtime.events import (
    RealtimeIncomingCallEvent,
    extract_sip_phone,
    sip_headers_as_dict,
)
from app.openai_realtime.prompt_builder import (
    ActiveAssistantConfigMissing,
    UnknownCalledNumber,
    resolve_clinic_by_called_number,
)
from app.openai_realtime.session import (
    accept_realtime_call,
    build_session_config,
    start_call_control_task,
)

router = APIRouter(prefix="/webhooks/openai", tags=["openai-realtime"])
logger = logging.getLogger(__name__)


class OpenAIWebhookVerificationError(ValueError):
    """Raised when the OpenAI SDK rejects a webhook signature."""


async def verify_openai_webhook_event(
    request: Request,
    settings: Settings,
) -> dict[str, Any]:
    """Verify and unwrap a webhook using the official OpenAI SDK."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", maxsplit=1)[0].strip().casefold() != (
        "application/json"
    ):
        raise OpenAIWebhookVerificationError(
            "OpenAI webhook must use application/json."
        )
    required_headers = (
        "webhook-id",
        "webhook-timestamp",
        "webhook-signature",
    )
    if any(not request.headers.get(name) for name in required_headers):
        raise OpenAIWebhookVerificationError(
            "OpenAI webhook signature headers are missing."
        )
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise OpenAIWebhookVerificationError(
                "Invalid webhook content length."
            ) from exc
        if declared_length > settings.max_webhook_body_bytes:
            raise OpenAIWebhookVerificationError("OpenAI webhook body is too large.")
    body = await request.body()
    if not body or len(body) > settings.max_webhook_body_bytes:
        raise OpenAIWebhookVerificationError(
            "OpenAI webhook body is empty or too large."
        )
    client = OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        webhook_secret=settings.openai_webhook_secret.get_secret_value(),
    )
    try:
        event = client.webhooks.unwrap(
            body.decode("utf-8"),
            dict(request.headers),
        )
    except (InvalidWebhookSignatureError, ValueError) as exc:
        raise OpenAIWebhookVerificationError(
            "Invalid OpenAI webhook signature."
        ) from exc
    if hasattr(event, "model_dump"):
        payload = event.model_dump(mode="json")
    elif isinstance(event, dict):
        payload = event
    else:
        raise OpenAIWebhookVerificationError("Unsupported OpenAI webhook payload.")
    if not isinstance(payload, dict):
        raise OpenAIWebhookVerificationError("Invalid OpenAI webhook payload.")
    return payload


def _mark_call_failed(
    session: Session,
    call_session: CallSession,
    *,
    reason: str,
) -> None:
    """Persist a terminal setup failure before returning an HTTP error."""
    state = dict(call_session.conversation_state_json)
    state["setup_error"] = reason
    call_session.conversation_state_json = state
    call_session.status = CallStatus.FAILED
    call_session.summary_text = reason
    call_session.ended_at = datetime.now(UTC)
    session.commit()


def _incoming_event_data(raw_event: dict[str, Any]) -> dict[str, Any]:
    """Return incoming webhook data as a safe dictionary."""
    data = raw_event.get("data")
    return data if isinstance(data, dict) else {}


@router.post("/realtime", status_code=status.HTTP_200_OK)
async def receive_realtime_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Verify, persist, accept, and start control for an incoming SIP call."""
    try:
        raw_event = await verify_openai_webhook_event(request, settings)
    except OpenAIWebhookVerificationError as exc:
        logger.warning("openai_webhook_signature_invalid")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature.",
        ) from exc

    if raw_event.get("type") != "realtime.call.incoming":
        logger.info(
            "openai_webhook_ignored",
            extra={"event_type": raw_event.get("type")},
        )
        return {"status": "ignored"}

    event_data = _incoming_event_data(raw_event)
    call_id_present = bool(event_data.get("call_id"))
    data_id_present = bool(event_data.get("id"))
    test_event = not call_id_present
    logger.info(
        "openai_realtime_incoming_received",
        extra={
            "event_type": raw_event.get("type"),
            "data_call_id_present": call_id_present,
            "data_id_present": data_id_present,
            "test_event": test_event,
        },
    )
    logger.info(
        "openai_hosted_sip_webhook_received",
        extra={
            "event_type": raw_event.get("type"),
            "data_call_id_present": call_id_present,
            "data_id_present": data_id_present,
            "test_event": test_event,
        },
    )
    if test_event:
        return {"ok": True, "test_event": True}

    try:
        incoming = RealtimeIncomingCallEvent.model_validate(raw_event)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid realtime.call.incoming payload.",
        ) from exc

    existing = session.scalar(
        select(CallSession)
        .where(CallSession.openai_call_id == incoming.data.call_id)
        .order_by(CallSession.created_at)
    )
    if existing is not None:
        logger.info(
            "realtime_incoming_duplicate",
            extra={
                "call_id": incoming.data.call_id,
                "call_session_id": str(existing.id),
            },
        )
        return {
            "status": "already_received",
            "call_session_id": str(existing.id),
        }

    sip_headers = sip_headers_as_dict(incoming.data.sip_headers)
    caller_phone = extract_sip_phone(sip_headers.get("from")) or "unknown"
    called_number = extract_sip_phone(sip_headers.get("to"))
    if called_number is None:
        logger.warning(
            "realtime_called_number_missing",
            extra={"call_id": incoming.data.call_id},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The incoming SIP call has no called number.",
        )
    provider_call_id = sip_headers.get("call-id")
    try:
        context = resolve_clinic_by_called_number(
            called_number,
            session=session,
        )
    except UnknownCalledNumber as exc:
        logger.warning(
            "realtime_called_number_unknown",
            extra={
                "call_id": incoming.data.call_id,
                "called_number": called_number,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No active clinic matches the called number.",
        ) from exc
    except ActiveAssistantConfigMissing as exc:
        logger.warning(
            "realtime_assistant_config_missing",
            extra={
                "call_id": incoming.data.call_id,
                "called_number": called_number,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The clinic has no active assistant configuration.",
        ) from exc
    clinic = context.clinic
    phone_number = context.phone_number
    assistant_config = context.active_assistant_config

    state: dict[str, Any] = {
        "webhook_event_id": incoming.id,
        "sip_headers": [
            header.model_dump(mode="json") for header in incoming.data.sip_headers
        ],
        "processed_tool_call_ids": [],
    }
    state["clinic_id"] = str(clinic.id)

    call_session = CallSession(
        clinic_id=clinic.id,
        phone_number_id=phone_number.id if phone_number is not None else None,
        assistant_config_id=assistant_config.id,
        openai_call_id=incoming.data.call_id,
        provider_call_id=(provider_call_id[:128] if provider_call_id else None),
        caller_phone=caller_phone[:32],
        called_number=called_number[:32],
        status=CallStatus.INCOMING,
        transcript_enabled=assistant_config.transcript_enabled,
        recording_enabled=assistant_config.recording_enabled,
        conversation_state_json=state,
    )
    session.add(call_session)
    session.flush()
    session.add(
        CallEvent(
            call_session_id=call_session.id,
            event_type=incoming.type,
            payload_json=raw_event,
        )
    )
    session.commit()

    logger.info(
        "realtime_incoming_persisted",
        extra={
            "call_id": incoming.data.call_id,
            "call_session_id": str(call_session.id),
            "caller_phone": caller_phone,
            "called_number": called_number,
        },
    )

    config = build_session_config(
        settings,
        call_session_id=call_session.id,
        caller_phone=caller_phone,
        context=context,
    )
    accept_payload = config.as_accept_payload()
    try:
        await accept_realtime_call(
            settings,
            call_id=incoming.data.call_id,
            payload=accept_payload,
        )
    except httpx.HTTPError as exc:
        fallback_voice = (config.fallback_voice or "").strip()
        if fallback_voice and fallback_voice != config.voice:
            fallback_payload = config.as_accept_payload()
            fallback_payload["audio"]["output"]["voice"] = fallback_voice
            try:
                logger.warning(
                    "realtime_accept_primary_voice_failed_trying_fallback",
                    extra={
                        "call_id": incoming.data.call_id,
                        "primary_voice": config.voice,
                        "fallback_voice": fallback_voice,
                    },
                )
                await accept_realtime_call(
                    settings,
                    call_id=incoming.data.call_id,
                    payload=fallback_payload,
                )
                accept_payload = fallback_payload
                config_voice = fallback_voice
            except httpx.HTTPError as fallback_exc:
                reason = "OpenAI could not accept the incoming call."
                _mark_call_failed(session, call_session, reason=reason)
                logger.exception(
                    "realtime_accept_failed",
                    extra={"call_id": incoming.data.call_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=reason,
                ) from fallback_exc
        else:
            config_voice = config.voice
            reason = "OpenAI could not accept the incoming call."
            _mark_call_failed(session, call_session, reason=reason)
            logger.exception(
                "realtime_accept_failed",
                extra={"call_id": incoming.data.call_id},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=reason,
            ) from exc
    else:
        config_voice = config.voice

    if accept_payload["audio"]["output"]["voice"] != config.voice:
        call_session.conversation_state_json = {
            **call_session.conversation_state_json,
            "fallback_voice_used": accept_payload["audio"]["output"]["voice"],
        }
        session.commit()

    try:
        start_call_control_task(
            settings=settings,
            call_session_id=call_session.id,
            clinic_id=clinic.id,
            openai_call_id=incoming.data.call_id,
            initial_message=config.initial_message,
            transcription_enabled=config.transcription_enabled,
        )
    except Exception as exc:
        reason = "Realtime control could not start."
        _mark_call_failed(session, call_session, reason=reason)
        logger.exception(
            "realtime_control_start_failed",
            extra={"call_id": incoming.data.call_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=reason,
        ) from exc

    logger.info(
        "realtime_call_accepted",
        extra={
            "call_id": incoming.data.call_id,
            "call_session_id": str(call_session.id),
            "model": config.model,
            "voice": config_voice,
        },
    )
    logger.info(
        "openai_hosted_sip_call_accepted",
        extra={
            "call_id": incoming.data.call_id,
            "call_session_id": str(call_session.id),
            "model": config.model,
            "voice": config_voice,
        },
    )
    return {
        "status": "accepted",
        "call_session_id": str(call_session.id),
    }
