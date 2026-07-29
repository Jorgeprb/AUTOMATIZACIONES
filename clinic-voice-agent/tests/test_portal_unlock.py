from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import AdminPrincipal
from app.enterprise_service import portal_access_state_for_account
from app.models import (
    AdminRole,
    AdminUser,
    BillingAccount,
    BillingAccountMember,
    BillingPrice,
    BillingProduct,
    Clinic,
    PhoneNumber,
    PhoneProvisioningOrder,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.utils.security import (
    _client_portal_path_allowed_while_locked,
    _enforce_client_portal_unlock,
)


def _request(path: str, method: str = "GET") -> Request:
    return Request({"type": "http", "path": path, "method": method, "headers": []})


def _account(db_session):
    user = AdminUser(
        username="owner@example.com",
        email="owner@example.com",
        password_hash="test",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
        auth_provider="password",
    )
    db_session.add(user)
    db_session.flush()
    account = BillingAccount(
        owner_user_id=user.id,
        display_name="Cuenta prueba",
        billing_email="owner@example.com",
        status="free",
    )
    db_session.add(account)
    db_session.flush()
    db_session.add(
        BillingAccountMember(
            billing_account_id=account.id,
            user_id=user.id,
            role="owner",
        )
    )
    clinic = Clinic(
        billing_account_id=account.id,
        name="Clínica prueba",
        timezone="Europe/Madrid",
        default_language="es",
        main_phone_number="pending-test",
        is_active=True,
    )
    db_session.add(clinic)
    db_session.flush()
    return account, clinic, user


def test_portal_starts_locked_and_unlocks_after_paid_phone_purchase(db_session):
    account, clinic, user = _account(db_session)
    initial = portal_access_state_for_account(db_session, account.id)
    assert initial.unlocked is False

    product = BillingProduct(
        code="phone_number",
        name="Número Autogal",
        product_type="one_time",
        ownership_type="permanent",
        entitlement_code="phone_number",
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    price = BillingPrice(
        product_id=product.id,
        code="phone_number_once",
        currency="EUR",
        unit_amount_minor=1500,
        billing_type="one_time",
        is_active=True,
    )
    db_session.add(price)
    db_session.flush()
    order = PurchaseOrder(
        billing_account_id=account.id,
        clinic_id=clinic.id,
        created_by_user_id=user.id,
        status="paid",
        currency="EUR",
        total_one_time_minor=1500,
        total_recurring_minor=0,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        PurchaseOrderItem(
            order_id=order.id,
            product_id=product.id,
            price_id=price.id,
            product_name_snapshot=product.name,
            unit_amount_minor=1500,
            quantity=1,
            billing_type="one_time",
        )
    )
    db_session.add(
        PhoneProvisioningOrder(
            billing_account_id=account.id,
            clinic_id=clinic.id,
            purchase_order_id=order.id,
            requested_by_user_id=user.id,
            status="paid_pending_provisioning",
            quantity=1,
        )
    )
    db_session.flush()

    state = portal_access_state_for_account(db_session, account.id)
    assert state.unlocked is True
    assert clinic.id in state.purchased_clinic_ids
    assert clinic.id in state.pending_activation_clinic_ids


def test_assigned_active_phone_unlocks_without_purchase(db_session):
    account, clinic, _ = _account(db_session)
    db_session.add(
        PhoneNumber(
            clinic_id=clinic.id,
            phone_number="+34881170001",
            label="Número asignado",
            is_active=True,
        )
    )
    db_session.flush()

    state = portal_access_state_for_account(db_session, account.id)
    assert state.unlocked is True
    assert clinic.id in state.assigned_phone_clinic_ids
    assert not state.purchased_clinic_ids


def test_locked_client_only_reaches_dashboard_clinics_and_billing():
    assert _client_portal_path_allowed_while_locked(_request("/api/billing/summary"))
    assert _client_portal_path_allowed_while_locked(_request("/api/admin/clinics"))
    assert _client_portal_path_allowed_while_locked(
        _request("/api/admin/clinics/12c145ab-b899-4da3-9a2e-173f4ddcf0e6/dashboard")
    )
    assert not _client_portal_path_allowed_while_locked(
        _request("/api/admin/clinics/12c145ab-b899-4da3-9a2e-173f4ddcf0e6/customers")
    )
    assert not _client_portal_path_allowed_while_locked(
        _request("/api/admin/clinics/12c145ab-b899-4da3-9a2e-173f4ddcf0e6/assistant-configs")
    )


def test_locked_non_superadmin_cannot_bypass_with_api_host(db_session):
    _, clinic, user = _account(db_session)
    principal = AdminPrincipal(
        user_id=user.id,
        username=user.username,
        display_name=None,
        email=user.email,
        avatar_url=None,
        role=AdminRole.CLINIC_ADMIN,
        clinic_ids=frozenset({clinic.id}),
        clinic_roles={clinic.id: AdminRole.CLINIC_ADMIN},
    )
    request = Request(
        {
            "type": "http",
            "path": f"/api/admin/clinics/{clinic.id}/customers",
            "method": "GET",
            "headers": [(b"host", b"voice.autogal.es")],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_client_portal_unlock(
            request, principal, db_session, object()  # settings is intentionally unused
        )

    assert exc_info.value.status_code == 402
