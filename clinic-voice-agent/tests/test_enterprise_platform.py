"""Focused tests for the enterprise CRM, billing and analysis additions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin.enterprise import (
    anonymize_customer,
    get_customer,
    replace_requirements,
)
from app.call_analysis_service import CallAnalysisPayload
from app.customer_service import normalize_phone_e164, validate_custom_values
from app.enterprise_schemas import ResourceRequirementPayload
from app.enterprise_service import (
    create_billing_account_for_user,
    create_clinic_for_account,
    has_active_entitlement,
    upsert_entitlement,
)
from app.models import (
    AdminRole,
    AdminUser,
    Appointment,
    BillingAccountMember,
    Clinic,
    ClinicCustomer,
    ClinicCustomerFieldDefinition,
    ClinicResource,
    Service,
    Worker,
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
    db_session.add_all([first, second])
    db_session.flush()
    phone = "+34693694989"
    db_session.add_all(
        [
            ClinicCustomer(
                clinic_id=first.id,
                name="Ana",
                normalized_phone=phone,
                display_phone=phone,
            ),
            ClinicCustomer(
                clinic_id=second.id,
                name="Ana",
                normalized_phone=phone,
                display_phone=phone,
            ),
        ]
    )
    db_session.commit()
    assert (
        db_session.scalar(
            select(ClinicCustomer).where(
                ClinicCustomer.clinic_id == first.id,
                ClinicCustomer.normalized_phone == phone,
            )
        )
        is not None
    )
    db_session.add(
        ClinicCustomer(
            clinic_id=first.id,
            name="Duplicado",
            normalized_phone=phone,
            display_phone=phone,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_customer_anonymization_fits_the_persisted_phone_column(
    db_session: Session,
) -> None:
    clinic = _clinic("Anonimización", "+34981000009")
    db_session.add(clinic)
    db_session.flush()
    customer = ClinicCustomer(
        clinic_id=clinic.id,
        name="Persona Identificable",
        normalized_phone="+34693694989",
        display_phone="+34 693 694 989",
        email="persona@example.test",
        notes="Dato personal",
        custom_values_json={"dato": "privado"},
    )
    db_session.add(customer)
    db_session.commit()

    result = anonymize_customer(clinic.id, customer.id, db_session)

    assert result.anonymized_at is not None
    assert result.personalization_enabled is False
    assert result.is_active is False
    assert len(result.normalized_phone) <= 32
    assert db_session.get(ClinicCustomer, customer.id) is not None


def test_customer_detail_accepts_appointment_without_service(
    db_session: Session,
) -> None:
    clinic = _clinic("Detalle CRM", "+34981000010")
    db_session.add(clinic)
    db_session.flush()
    customer = ClinicCustomer(
        clinic_id=clinic.id,
        name="Cliente sin servicio",
        normalized_phone="+34693694980",
        display_phone="+34693694980",
    )
    worker = Worker(
        clinic_id=clinic.id,
        name="Profesional",
        role="Médica",
        calendar_id="crm-detail@calendar.test",
    )
    db_session.add_all([customer, worker])
    db_session.flush()
    start_at = datetime.now(UTC) + timedelta(days=1)
    appointment = Appointment(
        clinic_id=clinic.id,
        worker_id=worker.id,
        service_id=None,
        customer_id=customer.id,
        google_calendar_id=worker.calendar_id,
        google_event_id="crm-detail-no-service",
        patient_name=customer.name,
        patient_phone=customer.normalized_phone,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
    )
    db_session.add(appointment)
    db_session.commit()

    detail = get_customer(clinic.id, customer.id, db_session)

    assert len(detail.appointments) == 1
    assert detail.appointments[0].service_id is None


def test_custom_values_reject_unknown_keys_and_validate_select(
    db_session: Session,
) -> None:
    clinic = _clinic("Campos", "+34981000003")
    db_session.add(clinic)
    db_session.flush()
    db_session.add_all(
        [
            ClinicCustomerFieldDefinition(
                clinic_id=clinic.id,
                key="alergias",
                label="Alergias",
                field_type="text",
                options_json=[],
                required=False,
                is_active=True,
                sort_order=1,
            ),
            ClinicCustomerFieldDefinition(
                clinic_id=clinic.id,
                key="preferencia",
                label="Preferencia",
                field_type="select",
                options_json=["mañana", "tarde"],
                required=True,
                is_active=True,
                sort_order=2,
            ),
        ]
    )
    db_session.commit()
    assert validate_custom_values(
        db_session,
        clinic_id=clinic.id,
        values={"alergias": "ninguna", "preferencia": "mañana"},
    ) == {"alergias": "ninguna", "preferencia": "mañana"}
    with pytest.raises(HTTPException) as unknown:
        validate_custom_values(
            db_session,
            clinic_id=clinic.id,
            values={"campo_ajeno": "x", "preferencia": "mañana"},
        )
    assert unknown.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_custom_values(
            db_session, clinic_id=clinic.id, values={"preferencia": "noche"}
        )


def test_commercial_owner_can_create_multiple_scoped_clinics(
    db_session: Session,
) -> None:
    user = AdminUser(
        username="owner@example.test",
        email="owner@example.test",
        display_name="Owner",
        password_hash="hash",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
        must_change_password=False,
        auth_provider="password",
    )
    db_session.add(user)
    db_session.flush()
    account = create_billing_account_for_user(
        db_session,
        user=user,
        display_name="Negocio",
        billing_email="owner@example.test",
    )
    first = create_clinic_for_account(
        db_session,
        account=account,
        owner=user,
        name="Clínica A",
        timezone="Europe/Madrid",
        main_phone_number="pending-a",
        email=None,
        address=None,
    )
    second = create_clinic_for_account(
        db_session,
        account=account,
        owner=user,
        name="Clínica B",
        timezone="Europe/Madrid",
        main_phone_number="pending-b",
        email=None,
        address=None,
    )
    db_session.commit()
    assert first.billing_account_id == account.id == second.billing_account_id
    membership = db_session.scalar(
        select(BillingAccountMember).where(
            BillingAccountMember.user_id == user.id,
            BillingAccountMember.billing_account_id == account.id,
        )
    )
    assert membership is not None and membership.role == "owner"


def test_entitlement_is_enforced_by_time_and_status(db_session: Session) -> None:
    user = AdminUser(
        username="billing@example.test",
        email="billing@example.test",
        password_hash="hash",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
        must_change_password=False,
        auth_provider="password",
    )
    db_session.add(user)
    db_session.flush()
    account = create_billing_account_for_user(
        db_session,
        user=user,
        display_name="Billing",
        billing_email="billing@example.test",
    )
    clinic = create_clinic_for_account(
        db_session,
        account=account,
        owner=user,
        name="Producción",
        timezone="Europe/Madrid",
        main_phone_number="pending-prod",
        email=None,
        address=None,
    )
    db_session.flush()
    assert not has_active_entitlement(
        db_session, clinic_id=clinic.id, code="assistant_production"
    )
    upsert_entitlement(
        db_session,
        clinic_id=clinic.id,
        billing_account_id=account.id,
        code="assistant_production",
        status_value="active",
        starts_at=datetime.now(UTC),
    )
    db_session.commit()
    assert has_active_entitlement(
        db_session, clinic_id=clinic.id, code="assistant_production"
    )


def test_call_analysis_payload_is_strict_and_contains_no_reasoning_field() -> None:
    payload = CallAnalysisPayload.model_validate(
        {
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
        }
    )
    assert payload.sentiment_label == "positive"
    assert "reasoning" not in payload.model_dump()
    with pytest.raises(ValueError):
        CallAnalysisPayload.model_validate(
            {
                "sentiment_label": "angry",
                "sentiment_score": 2,
                "confidence": 1,
                "urgency": "normal",
            }
        )


def test_duplicate_resource_requirements_are_rejected_before_commit(
    db_session: Session,
) -> None:
    clinic = _clinic("Recursos", "+34981000011")
    db_session.add(clinic)
    db_session.flush()
    service = Service(
        clinic_id=clinic.id,
        name="Servicio recursos",
        duration_minutes=30,
    )
    resource = ClinicResource(
        clinic_id=clinic.id,
        name="Recurso único",
        capacity=2,
    )
    db_session.add_all([service, resource])
    db_session.commit()
    duplicate = ResourceRequirementPayload(
        resource_id=resource.id,
        quantity=1,
    )

    with pytest.raises(HTTPException) as error:
        replace_requirements(
            clinic.id,
            service.id,
            [duplicate, duplicate],
            db_session,
        )

    assert error.value.status_code == 422
