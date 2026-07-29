"""Verified OpenAI Realtime incoming-call webhook."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import InvalidWebhookSignatureError, OpenAI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import CallEvent, CallSession, CallStatus, WebhookReceipt
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
_WEBHOOK_LEASE_TIMEOUT = timedelta(minutes=5)


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _claim_webhook(
    session: Session, *, event_id: str, event_type: str | None, payload: dict[str, Any]
) -> tuple[WebhookReceipt | None, bool]:
    """Claim a provider event once; return (receipt, duplicate)."""
    now = datetime.now(UTC)
    existing = session.scalar(
        select(WebhookReceipt)
        .where(
            WebhookReceipt.provider == "openai",
            WebhookReceipt.event_id == event_id,
        )
        .with_for_update()
    )
    if existing is not None:
        updated_at = existing.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        retryable = existing.status == "failed" or (
            existing.status == "processing"
            and updated_at <= now - _WEBHOOK_LEASE_TIMEOUT
        )
        if retryable:
            existing.attempts += 1
            existing.status = "processing"
            existing.last_error = None
            existing.processed_at = None
            session.commit()
            session.refresh(existing)
            return existing, False
        return existing, True
    receipt = WebhookReceipt(
        provider="openai",
        event_id=event_id[:200],
        event_type=(event_type or "")[:160] or None,
        payload_hash=_payload_hash(payload),
        status="processing",
    )
    session.add(receipt)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None, True
    session.refresh(receipt)
    return receipt, False


def _finish_webhook(
    session: Session, receipt: WebhookReceipt | None, *, error: str | None = None
) -> None:
    if receipt is None:
        return
    receipt.status = "failed" if error else "completed"
    receipt.last_error = error[:2000] if error else None
    receipt.processed_at = datetime.now(UTC)
    session.commit()


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

    provider_event_id = str(
        raw_event.get("id") or request.headers.get("webhook-id") or ""
    ).strip()
    if not provider_event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook event ID missing."
        )
    receipt, duplicate_delivery = _claim_webhook(
        session,
        event_id=provider_event_id,
        event_type=str(raw_event.get("type") or ""),
        payload=raw_event,
    )
    if duplicate_delivery:
        logger.info(
            "openai_webhook_duplicate", extra={"provider_event_id": provider_event_id}
        )
        return {"status": "already_received"}

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
        _finish_webhook(session, receipt)
        return {"ok": True, "test_event": True}

    try:
        incoming = RealtimeIncomingCallEvent.model_validate(raw_event)
    except ValidationError as exc:
        _finish_webhook(session, receipt, error="invalid_payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid realtime.call.incoming payload.",
        ) from exc

    existing = session.scalar(
        select(CallSession)
        .where(CallSession.openai_call_id == incoming.data.call_id)
        .order_by(CallSession.created_at)
    )
    retrying_failed_call = bool(
        existing is not None
        and existing.status == CallStatus.FAILED
        and existing.conversation_state_json.get("setup_error")
    )
    if existing is not None and not retrying_failed_call:
        logger.info(
            "realtime_incoming_duplicate",
            extra={
                "call_id": incoming.data.call_id,
                "call_session_id": str(existing.id),
            },
        )
        _finish_webhook(session, receipt)
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
        _finish_webhook(session, receipt, error="called_number_missing")
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
        _finish_webhook(session, receipt, error="unknown_called_number")
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
        _finish_webhook(session, receipt, error="assistant_config_missing")
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

    if existing is None:
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
    else:
        call_session = existing
        call_session.clinic_id = clinic.id
        call_session.phone_number_id = (
            phone_number.id if phone_number is not None else None
        )
        call_session.assistant_config_id = assistant_config.id
        call_session.provider_call_id = (
            provider_call_id[:128] if provider_call_id else None
        )
        call_session.caller_phone = caller_phone[:32]
        call_session.called_number = called_number[:32]
        call_session.status = CallStatus.INCOMING
        call_session.transcript_enabled = assistant_config.transcript_enabled
        call_session.recording_enabled = assistant_config.recording_enabled
        call_session.conversation_state_json = state
        call_session.ended_at = None
        call_session.summary_text = None
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
                _finish_webhook(session, receipt, error="accept_failed")
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
            _finish_webhook(session, receipt, error="accept_failed")
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
        _finish_webhook(session, receipt, error="control_start_failed")
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
    _finish_webhook(session, receipt)
    return {
        "status": "accepted",
        "call_session_id": str(call_session.id),
    }
