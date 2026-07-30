"""Regression tests for the global users/clinics administration view."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin.accounts import _serialize
from app.api.admin.enterprise import update_provisioning
from app.auth import AdminPrincipal
from app.enterprise_schemas import ProvisioningUpdate
from app.models import (
    AdminMembership,
    AdminRole,
    AdminUser,
    BillingAccount,
    Clinic,
    IntegrationOutbox,
    PhoneNumber,
    PhoneProvider,
    PhoneProvisioningOrder,
)


def _user(email: str, role: AdminRole = AdminRole.CLINIC_ADMIN) -> AdminUser:
    return AdminUser(
        username=email,
        email=email,
        display_name="Usuario de prueba",
        password_hash="hash",
        role=role,
        is_active=True,
        must_change_password=False,
        auth_provider="password",
    )


def _clinic(phone: str = "pending-admin-view") -> Clinic:
    return Clinic(
        name="Clínica de prueba",
        timezone="Europe/Madrid",
        default_language="es-ES",
        main_phone_number=phone,
        opening_hours_json={},
        data_retention_days=365,
        is_active=True,
    )


def test_admin_user_serialization_includes_clinics_numbers_and_pending_orders(
    db_session: Session,
) -> None:
    user = _user("owner@example.test")
    db_session.add(user)
    db_session.flush()
    account = BillingAccount(
        owner_user_id=user.id,
        display_name="Negocio de prueba",
        billing_email="owner@example.test",
        status="active",
        billing_address_json={},
    )
    db_session.add(account)
    db_session.flush()
    clinic = _clinic()
    clinic.billing_account_id = account.id
    db_session.add(clinic)
    db_session.flush()
    db_session.add(
        AdminMembership(
            user_id=user.id,
            clinic_id=clinic.id,
            role=AdminRole.CLINIC_ADMIN,
        )
    )
    db_session.add(
        PhoneNumber(
            clinic_id=clinic.id,
            provider=PhoneProvider.VOIPSTUDIO,
            phone_number="+34881170001",
            label="Número principal",
            is_active=True,
        )
    )
    pending = PhoneProvisioningOrder(
        billing_account_id=account.id,
        clinic_id=clinic.id,
        requested_by_user_id=user.id,
        status="paid_pending_provisioning",
        quantity=1,
    )
    db_session.add(pending)
    db_session.commit()

    payload = _serialize(db_session, user)

    assert len(payload.memberships) == 1
    membership = payload.memberships[0]
    assert membership.clinic_name == clinic.name
    assert [phone.phone_number for phone in membership.phone_numbers] == [
        "+34881170001"
    ]
    assert [item.id for item in membership.pending_provisioning] == [pending.id]


def test_activating_pending_number_assigns_clinic_and_enqueues_email(
    db_session: Session,
) -> None:
    admin = _user("admin@example.test", AdminRole.SUPER_ADMIN)
    owner = _user("owner@example.test")
    db_session.add_all([admin, owner])
    db_session.flush()
    account = BillingAccount(
        owner_user_id=owner.id,
        display_name="Negocio de prueba",
        billing_email="configured@example.test",
        status="active",
        billing_address_json={},
    )
    db_session.add(account)
    db_session.flush()
    clinic = _clinic("pending-activation")
    clinic.billing_account_id = account.id
    db_session.add(clinic)
    db_session.flush()
    order = PhoneProvisioningOrder(
        billing_account_id=account.id,
        clinic_id=clinic.id,
        requested_by_user_id=owner.id,
        status="paid_pending_provisioning",
        quantity=1,
    )
    db_session.add(order)
    db_session.commit()

    principal = AdminPrincipal(
        user_id=admin.id,
        username=admin.username,
        display_name=admin.display_name,
        email=admin.email,
        avatar_url=None,
        role=AdminRole.SUPER_ADMIN,
        clinic_ids=frozenset(),
        clinic_roles={},
    )
    result = update_provisioning(
        order.id,
        ProvisioningUpdate(
            assigned_number="+34881170002",
            provider="voip_studio",
            external_provider_id="provider-123",
            sip_target="sip:bot@sip.autogal.es:6060;transport=udp",
            webhook_url="https://voice.autogal.es/webhook",
            notes="Activado desde usuarios y clínicas",
            status="active",
        ),
        db_session,
        principal,
    )

    assert result.status == "active"
    db_session.refresh(clinic)
    assert clinic.main_phone_number == "+34881170002"
    phone = db_session.scalar(
        select(PhoneNumber).where(PhoneNumber.phone_number == "+34881170002")
    )
    assert phone is not None
    assert phone.label == "Número Autogal"
    assert phone.provider == PhoneProvider.VOIPSTUDIO
    assert phone.sip_target == "sip:bot@sip.autogal.es:6060;transport=udp"
    assert phone.webhook_url == "https://voice.autogal.es/webhook"
    email_job = db_session.scalar(
        select(IntegrationOutbox).where(
            IntegrationOutbox.dedupe_key == f"number-active:{order.id}"
        )
    )
    assert email_job is not None
    assert email_job.kind == "email.send"
    assert email_job.payload_json["template"] == "number_activated"
