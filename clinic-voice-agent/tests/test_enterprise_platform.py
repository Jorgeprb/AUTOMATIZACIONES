"""Focused tests for the enterprise CRM, billing and analysis additions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.call_analysis_service import CallAnalysisPayload
from app.customer_service import normalize_phone_e164, validate_custom_values
from app.enterprise_service import (
    create_billing_account_for_user,
    create_clinic_for_account,
    has_active_entitlement,
    upsert_entitlement,
)
from app.models import (
    AdminRole,
    AdminUser,
    BillingAccountMember,
    Clinic,
    ClinicCustomer,
    ClinicCustomerFieldDefinition,
)


def _clinic(name: str, phone: str) -> Clinic:
    return Clinic(
        name=name,
        timezone="Europe/Madrid",
        default_language="es-ES",
        main_phone_number=phone,
        opening_hours_json={},
        data_retention_days=365,
        is_active=True,
    )


def test_phone_normalization_to_e164() -> None:
    assert normalize_phone_e164("881 17 08 37", default_region="ES") == "+34881170837"
    assert normalize_phone_e164("+34 693 694 989") == "+34693694989"


def test_customer_phone_is_unique_only_inside_one_clinic(db_session: Session) -> None:
    first = _clinic("Uno", "+34981000001")
    second = _clinic("Dos", "+34981000002")
    db_session.add_all([first, second]); db_session.flush()
    phone = "+34693694989"
    db_session.add_all([
        ClinicCustomer(clinic_id=first.id, name="Ana", normalized_phone=phone, display_phone=phone),
        ClinicCustomer(clinic_id=second.id, name="Ana", normalized_phone=phone, display_phone=phone),
    ])
    db_session.commit()
    assert db_session.scalar(select(ClinicCustomer).where(ClinicCustomer.clinic_id == first.id, ClinicCustomer.normalized_phone == phone)) is not None
    db_session.add(ClinicCustomer(clinic_id=first.id, name="Duplicado", normalized_phone=phone, display_phone=phone))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_custom_values_reject_unknown_keys_and_validate_select(db_session: Session) -> None:
    clinic = _clinic("Campos", "+34981000003")
    db_session.add(clinic); db_session.flush()
    db_session.add_all([
        ClinicCustomerFieldDefinition(clinic_id=clinic.id, key="alergias", label="Alergias", field_type="text", options_json=[], required=False, is_active=True, sort_order=1),
        ClinicCustomerFieldDefinition(clinic_id=clinic.id, key="preferencia", label="Preferencia", field_type="select", options_json=["mañana", "tarde"], required=True, is_active=True, sort_order=2),
    ])
    db_session.commit()
    assert validate_custom_values(db_session, clinic_id=clinic.id, values={"alergias": "ninguna", "preferencia": "mañana"}) == {"alergias": "ninguna", "preferencia": "mañana"}
    with pytest.raises(HTTPException) as unknown:
        validate_custom_values(db_session, clinic_id=clinic.id, values={"campo_ajeno": "x", "preferencia": "mañana"})
    assert unknown.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_custom_values(db_session, clinic_id=clinic.id, values={"preferencia": "noche"})


def test_commercial_owner_can_create_multiple_scoped_clinics(db_session: Session) -> None:
    user = AdminUser(username="owner@example.test", email="owner@example.test", display_name="Owner", password_hash="hash", role=AdminRole.CLINIC_ADMIN, is_active=True, must_change_password=False, auth_provider="password")
    db_session.add(user); db_session.flush()
    account = create_billing_account_for_user(db_session, user=user, display_name="Negocio", billing_email="owner@example.test")
    first = create_clinic_for_account(db_session, account=account, owner=user, name="Clínica A", timezone="Europe/Madrid", main_phone_number="pending-a", email=None, address=None)
    second = create_clinic_for_account(db_session, account=account, owner=user, name="Clínica B", timezone="Europe/Madrid", main_phone_number="pending-b", email=None, address=None)
    db_session.commit()
    assert first.billing_account_id == account.id == second.billing_account_id
    membership = db_session.scalar(select(BillingAccountMember).where(BillingAccountMember.user_id == user.id, BillingAccountMember.billing_account_id == account.id))
    assert membership is not None and membership.role == "owner"


def test_entitlement_is_enforced_by_time_and_status(db_session: Session) -> None:
    user = AdminUser(username="billing@example.test", email="billing@example.test", password_hash="hash", role=AdminRole.CLINIC_ADMIN, is_active=True, must_change_password=False, auth_provider="password")
    db_session.add(user); db_session.flush()
    account = create_billing_account_for_user(db_session, user=user, display_name="Billing", billing_email="billing@example.test")
    clinic = create_clinic_for_account(db_session, account=account, owner=user, name="Producción", timezone="Europe/Madrid", main_phone_number="pending-prod", email=None, address=None)
    db_session.flush()
    assert not has_active_entitlement(db_session, clinic_id=clinic.id, code="assistant_production")
    upsert_entitlement(db_session, clinic_id=clinic.id, billing_account_id=account.id, code="assistant_production", status_value="active", starts_at=datetime.now(UTC))
    db_session.commit()
    assert has_active_entitlement(db_session, clinic_id=clinic.id, code="assistant_production")


def test_call_analysis_payload_is_strict_and_contains_no_reasoning_field() -> None:
    payload = CallAnalysisPayload.model_validate({
        "sentiment_label": "positive",
        "sentiment_score": 0.7,
        "confidence": 0.9,
        "intent": "booking",
        "resolved": True,
        "resolution_label": "appointment_created",
        "urgency": "normal",
        "topics": ["appointment"],
        "friction_points": [],
        "summary": "La persona reservó una cita.",
    })
    assert payload.sentiment_label == "positive"
    assert "reasoning" not in payload.model_dump()
    with pytest.raises(ValueError):
        CallAnalysisPayload.model_validate({"sentiment_label": "angry", "sentiment_score": 2, "confidence": 1, "urgency": "normal"})
