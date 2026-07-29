"""Shared conversation policy and state helpers for calls and test chats."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import AssistantConfig

ConversationIntent = Literal[
    "information",
    "pricing",
    "create_appointment",
    "cancel_appointment",
    "reschedule_appointment",
    "faq",
    "transfer_to_human",
    "commercial_call",
    "medical_emergency",
    "close_conversation",
]


class ConversationPolicy(BaseModel):
    """Editable, non-rigid behavior policy rendered into the assistant prompt."""

    style: Literal["natural", "formal", "comercial", "breve"] = "natural"
    initiative_level: Literal["bajo", "medio", "alto"] = "medio"
    max_consecutive_questions: int = Field(default=2, ge=1, le=5)
    max_proposed_slots: int = Field(default=3, ge=1, le=10)
    allow_bookings: bool = True
    allow_cancellations: bool = True
    allow_reschedules: bool = True
    allow_price_answers: bool = True
    allow_booking_without_worker: bool = True
    ask_patient_name: bool = True
    ask_patient_phone: bool = True
    ask_general_reason: bool = True
    ask_service: bool = True
    service_prompt_mode: Literal["list_services", "ask_open", "infer_confirm"] = (
        "ask_open"
    )
    direct_availability_response: bool = True
    direct_booking_response: bool = True
    post_booking_followup_enabled: bool = True
    hangup_after_no_more_help: bool = True
    hangup_on_natural_goodbye: bool = True
    commercial_call_handling: Literal["declinar", "transferir", "responder_basico"] = (
        "declinar"
    )
    human_transfer_rules: str | None = None
    commercial_call_message: str | None = None
    no_availability_message: str | None = None
    emergency_message: str | None = None
    additional_rules: str | None = None


class ConversationState(BaseModel):
    """Persisted lightweight state used by Realtime calls and the test console."""

    intent: ConversationIntent | None = None
    service: dict[str, Any] | None = None
    worker: dict[str, Any] | None = None
    preferred_date: str | None = None
    preferred_time: str | None = None
    preferred_time_window: str | None = None
    pending_slots: list[dict[str, Any]] = Field(default_factory=list)
    selected_slot: dict[str, Any] | None = None
    patient_name: str | None = None
    patient_phone: str | None = None
    appointment_id: str | None = None
    awaiting_confirmation: bool = False
    last_user_acceptance: str | None = None


def conversation_policy_from_config(config: AssistantConfig) -> ConversationPolicy:
    """Build the effective policy from an AssistantConfig row."""
    return ConversationPolicy(
        style=config.conversation_style,
        initiative_level=config.initiative_level,
        max_consecutive_questions=config.max_consecutive_questions,
        max_proposed_slots=config.max_proposed_slots,
        allow_bookings=config.allow_bookings,
        allow_cancellations=config.allow_cancellations,
        allow_reschedules=config.allow_reschedules,
        allow_price_answers=config.allow_price_answers,
        allow_booking_without_worker=config.allow_booking_without_worker,
        ask_patient_name=config.ask_patient_name,
        ask_patient_phone=config.ask_patient_phone,
        ask_general_reason=config.ask_general_reason,
        ask_service=config.ask_service,
        service_prompt_mode=config.service_prompt_mode,
        direct_availability_response=config.direct_availability_response,
        direct_booking_response=config.direct_booking_response,
        post_booking_followup_enabled=config.post_booking_followup_enabled,
        hangup_after_no_more_help=config.hangup_after_no_more_help,
        hangup_on_natural_goodbye=config.hangup_on_natural_goodbye,
        commercial_call_handling=config.commercial_call_handling,
        human_transfer_rules=config.human_transfer_rules,
        commercial_call_message=config.commercial_call_message,
        no_availability_message=config.no_availability_message,
        emergency_message=config.emergency_message,
        additional_rules=config.conversation_extra_rules,
    )


def load_conversation_state(payload: dict[str, Any] | None) -> ConversationState:
    """Read a persisted JSON state without failing on older ad-hoc keys."""
    if not payload:
        return ConversationState()
    known = {
        key: value
        for key, value in payload.items()
        if key in ConversationState.model_fields
    }
    return ConversationState.model_validate(known)


def merge_conversation_state(
    payload: dict[str, Any] | None,
    **updates: Any,
) -> dict[str, Any]:
    """Merge typed conversation-state fields while preserving legacy runtime keys."""
    base = dict(payload or {})
    state = load_conversation_state(base)
    for key, value in updates.items():
        if key in ConversationState.model_fields:
            setattr(state, key, value)
    base.update(state.model_dump(mode="json"))
    return base
