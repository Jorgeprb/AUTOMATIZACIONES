"""Regression tests for client-portal clinic creation."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.enterprise_service import (
    create_billing_account_for_user,
    create_clinic_for_account,
)
from app.models import AdminRole, AdminUser


def test_multiple_pending_clinics_receive_unique_internal_numbers(
    db_session: Session,
) -> None:
    user = AdminUser(
        username="owner-clinics@example.test",
        email="owner-clinics@example.test",
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
        display_name="Cuenta",
        billing_email=user.email or user.username,
    )
    first = create_clinic_for_account(
        db_session,
        account=account,
        owner=user,
        name="Clínica uno",
        timezone="Europe/Madrid",
        main_phone_number="pending",
        email=None,
        address=None,
    )
    second = create_clinic_for_account(
        db_session,
        account=account,
        owner=user,
        name="Clínica dos",
        timezone="Europe/Madrid",
        main_phone_number="pending",
        email=None,
        address=None,
    )
    db_session.commit()

    assert first.main_phone_number.startswith("pending-")
    assert second.main_phone_number.startswith("pending-")
    assert first.main_phone_number != second.main_phone_number
    assert first.billing_account_id == second.billing_account_id == account.id
