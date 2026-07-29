"""Enterprise domain helpers for tenants, billing, entitlements and outbox jobs."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AdminPrincipal
from app.config import Settings
from app.models import (
    AdminMembership,
    AdminRole,
    AdminUser,
    AuthActionToken,
    BillingAccount,
    BillingAccountMember,
    BillingPrice,
    BillingProduct,
    Clinic,
    ClinicEntitlement,
    IntegrationOutbox,
)

PRODUCTION_ENTITLEMENT_CODES = frozenset({"assistant_production", "phone_number"})


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("A valid email address is required.")
    return normalized


def require_principal_user(principal: AdminPrincipal) -> uuid.UUID:
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires a portal user account.",
        )
    return principal.user_id


def account_for_user(session: Session, user_id: uuid.UUID) -> BillingAccount | None:
    return session.scalar(
        select(BillingAccount)
        .join(
            BillingAccountMember,
            BillingAccountMember.billing_account_id == BillingAccount.id,
        )
        .where(BillingAccountMember.user_id == user_id)
        .order_by(BillingAccount.created_at)
    )


def require_account_for_principal(
    session: Session,
    principal: AdminPrincipal,
) -> BillingAccount:
    user_id = require_principal_user(principal)
    account = account_for_user(session, user_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete commercial account onboarding first.",
        )
    return account


def create_billing_account_for_user(
    session: Session,
    *,
    user: AdminUser,
    display_name: str,
    billing_email: str,
) -> BillingAccount:
    existing = account_for_user(session, user.id)
    if existing is not None:
        return existing
    account = BillingAccount(
        owner_user_id=user.id,
        display_name=display_name.strip() or user.display_name or user.username,
        billing_email=normalize_email(billing_email),
        status="free",
        billing_address_json={},
    )
    session.add(account)
    session.flush()
    session.add(
        BillingAccountMember(
            billing_account_id=account.id,
            user_id=user.id,
            role="owner",
        )
    )
    return account


def create_clinic_for_account(
    session: Session,
    *,
    account: BillingAccount,
    owner: AdminUser,
    name: str,
    timezone: str,
    main_phone_number: str,
    email: str | None,
    address: str | None,
) -> Clinic:
    requested_phone = main_phone_number.strip()
    if not requested_phone or requested_phone.casefold() in {
        "pending",
        "pendiente",
        "pending-assignment",
    }:
        requested_phone = f"pending-{uuid.uuid4().hex[:20]}"
    clinic = Clinic(
        billing_account_id=account.id,
        name=name.strip(),
        timezone=timezone,
        default_language="gl-ES",
        main_phone_number=requested_phone,
        email=email.strip().casefold() if email else None,
        address=address.strip() if address else None,
        is_active=True,
    )
    session.add(clinic)
    session.flush()
    membership = session.scalar(
        select(AdminMembership).where(
            AdminMembership.user_id == owner.id,
            AdminMembership.clinic_id == clinic.id,
        )
    )
    if membership is None:
        session.add(
            AdminMembership(
                user_id=owner.id,
                clinic_id=clinic.id,
                role=AdminRole.CLINIC_ADMIN,
            )
        )
    return clinic


def require_account_clinic(
    session: Session,
    *,
    account: BillingAccount,
    clinic_id: uuid.UUID,
) -> Clinic:
    clinic = session.scalar(
        select(Clinic).where(
            Clinic.id == clinic_id,
            Clinic.billing_account_id == account.id,
        )
    )
    if clinic is None:
        raise HTTPException(status_code=404, detail="Clinic not found in this account.")
    return clinic


def has_active_entitlement(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    code: str,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    entitlement = session.scalar(
        select(ClinicEntitlement).where(
            ClinicEntitlement.clinic_id == clinic_id,
            ClinicEntitlement.code == code,
            ClinicEntitlement.status == "active",
            (
                ClinicEntitlement.starts_at.is_(None)
                | (ClinicEntitlement.starts_at <= current)
            ),
            (
                ClinicEntitlement.ends_at.is_(None)
                | (ClinicEntitlement.ends_at > current)
            ),
        )
    )
    return entitlement is not None


def require_production_entitlement(session: Session, clinic_id: uuid.UUID) -> None:
    if not has_active_entitlement(
        session,
        clinic_id=clinic_id,
        code="assistant_production",
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="An active Autogal service subscription is required.",
        )


def upsert_entitlement(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    billing_account_id: uuid.UUID,
    code: str,
    status_value: str,
    quantity: int = 1,
    subscription_id: uuid.UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> ClinicEntitlement:
    row = session.scalar(
        select(ClinicEntitlement).where(
            ClinicEntitlement.clinic_id == clinic_id,
            ClinicEntitlement.code == code,
        )
    )
    if row is None:
        row = ClinicEntitlement(
            clinic_id=clinic_id,
            billing_account_id=billing_account_id,
            code=code,
            status=status_value,
            quantity=quantity,
            subscription_id=subscription_id,
            starts_at=starts_at,
            ends_at=ends_at,
            metadata_json=metadata or {},
        )
        session.add(row)
    else:
        row.billing_account_id = billing_account_id
        row.status = status_value
        row.quantity = quantity
        row.subscription_id = subscription_id
        row.starts_at = starts_at
        row.ends_at = ends_at
        row.metadata_json = metadata or row.metadata_json
    return row


def enqueue_outbox(
    session: Session,
    *,
    kind: str,
    dedupe_key: str,
    payload: dict[str, Any],
) -> IntegrationOutbox:
    row = session.scalar(
        select(IntegrationOutbox).where(IntegrationOutbox.dedupe_key == dedupe_key)
    )
    if row is not None:
        if row.status in {"dead_letter", "failed"}:
            row.status = "pending"
            row.next_attempt_at = datetime.now(UTC)
            row.last_error = None
        return row
    row = IntegrationOutbox(
        kind=kind,
        dedupe_key=dedupe_key,
        payload_json=payload,
        status="pending",
        next_attempt_at=datetime.now(UTC),
    )
    session.add(row)
    return row


def create_action_token(
    session: Session,
    *,
    user_id: uuid.UUID,
    kind: str,
    ttl: timedelta,
) -> str:
    raw = secrets.token_urlsafe(48)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    token = AuthActionToken(
        user_id=user_id,
        kind=kind,
        token_hash=digest,
        expires_at=datetime.now(UTC) + ttl,
    )
    session.add(token)
    return raw


def consume_action_token(
    session: Session,
    *,
    raw_token: str,
    kind: str,
) -> AuthActionToken | None:
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    candidate = session.scalar(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == digest,
            AuthActionToken.kind == kind,
        )
    )
    if candidate is None:
        return None
    active_tokens = list(
        session.scalars(
            select(AuthActionToken)
            .where(
                AuthActionToken.user_id == candidate.user_id,
                AuthActionToken.kind == kind,
                AuthActionToken.used_at.is_(None),
            )
            .order_by(AuthActionToken.id)
            .with_for_update()
        )
    )
    row = next((item for item in active_tokens if item.token_hash == digest), None)
    now = datetime.now(UTC)
    if row is None or row.expires_at <= now:
        return None
    for token in active_tokens:
        token.used_at = now
    return row


def sync_catalog_from_settings(session: Session, settings: Settings) -> None:
    """Keep server-side Stripe IDs synchronized without changing server prices."""
    mapping = {
        "phone_number_once": settings.stripe_phone_price_id.strip(),
        "monthly_service": settings.stripe_monthly_service_price_id.strip(),
    }
    for code, stripe_id in mapping.items():
        if not stripe_id:
            continue
        price = session.scalar(select(BillingPrice).where(BillingPrice.code == code))
        if price is not None and price.stripe_price_id != stripe_id:
            price.stripe_price_id = stripe_id


def catalog_rows(session: Session) -> list[tuple[BillingProduct, list[BillingPrice]]]:
    products = list(
        session.scalars(
            select(BillingProduct)
            .where(BillingProduct.is_active.is_(True))
            .order_by(BillingProduct.name)
        )
    )
    prices = list(
        session.scalars(
            select(BillingPrice)
            .where(BillingPrice.is_active.is_(True))
            .order_by(BillingPrice.unit_amount_minor)
        )
    )
    grouped: dict[uuid.UUID, list[BillingPrice]] = {}
    for price in prices:
        grouped.setdefault(price.product_id, []).append(price)
    return [(product, grouped.get(product.id, [])) for product in products]
