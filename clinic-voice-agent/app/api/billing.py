"""Authenticated commercial account and Stripe Billing API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import AdminPrincipal
from app.config import Settings, get_settings
from app.db import get_db
from app.enterprise_schemas import (
    BillingAccountRead,
    CatalogItem,
    CheckoutRequest,
    CheckoutResponse,
    CommercialSummary,
    EntitlementRead,
    OrderRead,
    PaymentRead,
    ProvisioningRead,
    SubscriptionRead,
)
from app.enterprise_service import (
    catalog_rows,
    require_account_clinic,
    require_account_for_principal,
    sync_catalog_from_settings,
)
from app.models import (
    AdminUser,
    BillingAccountMember,
    BillingPrice,
    BillingProduct,
    Clinic,
    ClinicEntitlement,
    ClinicSubscription,
    PaymentRecord,
    PhoneNumber,
    PhoneProvisioningOrder,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.utils.security import require_admin_access

router = APIRouter(prefix="/api/billing", tags=["Billing"])


def _stripe(settings: Settings) -> None:
    key = settings.stripe_secret_key.get_secret_value().strip()
    if not key:
        raise HTTPException(status_code=503, detail="Stripe is not configured.")
    stripe.api_key = key


def _account_read(session: Session, account) -> BillingAccountRead:
    owner = session.get(AdminUser, account.owner_user_id)
    return BillingAccountRead(
        **BillingAccountRead.model_validate(account).model_dump(
            exclude={"clinic_count", "user_count", "owner_email", "owner_name"}
        ),
        clinic_count=session.scalar(
            select(func.count(Clinic.id)).where(Clinic.billing_account_id == account.id)
        ) or 0,
        user_count=session.scalar(
            select(func.count(BillingAccountMember.id)).where(
                BillingAccountMember.billing_account_id == account.id
            )
        ) or 0,
        owner_email=(owner.email or owner.username) if owner else None,
        owner_name=(owner.display_name or owner.username) if owner else None,
    )


@router.get("/catalog", response_model=list[CatalogItem])
def catalog(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> list[CatalogItem]:
    sync_catalog_from_settings(session, settings); session.commit()
    return [CatalogItem(product=product, prices=prices) for product, prices in catalog_rows(session)]


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    payload: CheckoutRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> CheckoutResponse:
    _stripe(settings)
    account = require_account_for_principal(session, principal)
    require_account_clinic(session, account=account, clinic_id=payload.clinic_id)
    sync_catalog_from_settings(session, settings)
    price_ids = {line.price_id for line in payload.lines}
    rows = list(session.scalars(select(BillingPrice).where(BillingPrice.id.in_(price_ids), BillingPrice.is_active.is_(True))))
    by_id = {row.id: row for row in rows}
    if set(by_id) != price_ids:
        raise HTTPException(status_code=422, detail="One or more catalog prices are invalid.")
    stripe_lines = []
    one_time = recurring = 0
    order = PurchaseOrder(
        billing_account_id=account.id,
        clinic_id=payload.clinic_id,
        created_by_user_id=principal.user_id,
        status="checkout_pending",
        currency="EUR",
        total_one_time_minor=0,
        total_recurring_minor=0,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(order); session.flush()
    has_recurring = False
    for line in payload.lines:
        price = by_id[line.price_id]
        product = session.get(BillingProduct, price.product_id)
        if product is None or not price.stripe_price_id:
            raise HTTPException(status_code=503, detail="Catalog price is not synchronized with Stripe.")
        subtotal = price.unit_amount_minor * line.quantity
        if price.billing_type == "recurring":
            recurring += subtotal; has_recurring = True
        else:
            one_time += subtotal
        stripe_lines.append({"price": price.stripe_price_id, "quantity": line.quantity})
        session.add(PurchaseOrderItem(order_id=order.id, product_id=product.id, price_id=price.id, product_name_snapshot=product.name, unit_amount_minor=price.unit_amount_minor, quantity=line.quantity, billing_type=price.billing_type, stripe_price_id_snapshot=price.stripe_price_id))
    order.total_one_time_minor = one_time; order.total_recurring_minor = recurring
    customer_id = account.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(name=account.display_name, email=account.billing_email, metadata={"billing_account_id": str(account.id)})
        customer_id = customer["id"]; account.stripe_customer_id = customer_id
    mode = "subscription" if has_recurring else "payment"
    kwargs = {
        "mode": mode,
        "customer": customer_id,
        "line_items": stripe_lines,
        "success_url": settings.stripe_success_url,
        "cancel_url": settings.stripe_cancel_url,
        "client_reference_id": str(order.id),
        "metadata": {"order_id": str(order.id), "billing_account_id": str(account.id), "clinic_id": str(payload.clinic_id)},
        "allow_promotion_codes": True,
    }
    if mode == "subscription":
        kwargs["subscription_data"] = {"metadata": {"order_id": str(order.id), "clinic_id": str(payload.clinic_id), "billing_account_id": str(account.id)}}
    checkout = stripe.checkout.Session.create(**kwargs)
    order.stripe_checkout_session_id = checkout["id"]
    order.checkout_url = checkout["url"]
    session.commit()
    return CheckoutResponse(order_id=order.id, checkout_url=str(checkout["url"]))


@router.get("/orders/{order_id}", response_model=OrderRead)
def order_status(order_id: uuid.UUID, session: Annotated[Session, Depends(get_db)], principal: Annotated[AdminPrincipal, Depends(require_admin_access)]) -> OrderRead:
    account = require_account_for_principal(session, principal)
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id, PurchaseOrder.billing_account_id == account.id))
    if order is None: raise HTTPException(status_code=404, detail="Order not found.")
    return OrderRead.model_validate(order)


@router.get("/summary", response_model=CommercialSummary)
def commercial_summary(session: Annotated[Session, Depends(get_db)], principal: Annotated[AdminPrincipal, Depends(require_admin_access)]) -> CommercialSummary:
    account = require_account_for_principal(session, principal)
    orders = list(session.scalars(select(PurchaseOrder).where(PurchaseOrder.billing_account_id == account.id).order_by(PurchaseOrder.created_at.desc())))
    subs = list(session.scalars(select(ClinicSubscription).where(ClinicSubscription.billing_account_id == account.id).order_by(ClinicSubscription.created_at.desc())))
    payments = list(session.scalars(select(PaymentRecord).where(PaymentRecord.billing_account_id == account.id).order_by(PaymentRecord.created_at.desc())))
    provisioning = list(session.scalars(select(PhoneProvisioningOrder).where(PhoneProvisioningOrder.billing_account_id == account.id).order_by(PhoneProvisioningOrder.created_at.desc())))
    entitlements = list(session.scalars(select(ClinicEntitlement).where(ClinicEntitlement.billing_account_id == account.id)))
    phones = list(session.scalars(select(PhoneNumber.phone_number).join(Clinic, Clinic.id == PhoneNumber.clinic_id).where(Clinic.billing_account_id == account.id, PhoneNumber.is_active.is_(True))))
    return CommercialSummary(
        account=_account_read(session, account),
        orders=[OrderRead.model_validate(row) for row in orders],
        subscriptions=[SubscriptionRead.model_validate(row) for row in subs],
        payments=[PaymentRead.model_validate(row) for row in payments],
        provisioning=[ProvisioningRead.model_validate(row) for row in provisioning],
        entitlements=[EntitlementRead.model_validate(row) for row in entitlements],
        phone_numbers=phones,
        can_use_production=any(row.code == "assistant_production" and row.status == "active" for row in entitlements),
    )


@router.post("/portal", response_model=dict)
def customer_portal(session: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)], principal: Annotated[AdminPrincipal, Depends(require_admin_access)]) -> dict[str, str]:
    _stripe(settings)
    account = require_account_for_principal(session, principal)
    if not account.stripe_customer_id: raise HTTPException(status_code=409, detail="No Stripe customer exists yet.")
    portal = stripe.billing_portal.Session.create(customer=account.stripe_customer_id, return_url=settings.stripe_customer_portal_return_url)
    return {"url": str(portal["url"])}


@router.post("/subscriptions/{subscription_id}/cancel", status_code=202)
def cancel_subscription(subscription_id: uuid.UUID, session: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)], principal: Annotated[AdminPrincipal, Depends(require_admin_access)]) -> dict[str, str]:
    _stripe(settings)
    account = require_account_for_principal(session, principal)
    row = session.scalar(select(ClinicSubscription).where(ClinicSubscription.id == subscription_id, ClinicSubscription.billing_account_id == account.id))
    if row is None: raise HTTPException(status_code=404, detail="Subscription not found.")
    stripe.Subscription.modify(row.stripe_subscription_id, cancel_at_period_end=True)
    return {"status": "pending_webhook"}


@router.post("/subscriptions/{subscription_id}/reactivate", status_code=202)
def reactivate_subscription(subscription_id: uuid.UUID, session: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)], principal: Annotated[AdminPrincipal, Depends(require_admin_access)]) -> dict[str, str]:
    _stripe(settings)
    account = require_account_for_principal(session, principal)
    row = session.scalar(select(ClinicSubscription).where(ClinicSubscription.id == subscription_id, ClinicSubscription.billing_account_id == account.id))
    if row is None: raise HTTPException(status_code=404, detail="Subscription not found.")
    stripe.Subscription.modify(row.stripe_subscription_id, cancel_at_period_end=False)
    return {"status": "pending_webhook"}
