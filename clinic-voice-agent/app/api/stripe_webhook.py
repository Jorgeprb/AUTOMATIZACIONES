"""Verified and idempotent Stripe webhook projection."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.enterprise_service import enqueue_outbox, upsert_entitlement
from app.models import (
    BillingAccount,
    BillingPrice,
    BillingProduct,
    ClinicSubscription,
    PaymentRecord,
    PhoneProvisioningOrder,
    PurchaseOrder,
    PurchaseOrderItem,
    WebhookReceipt,
)

router = APIRouter(tags=["Stripe webhooks"])


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    return dict(value)


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def _order_from_object(session: Session, data: dict[str, Any]) -> PurchaseOrder | None:
    metadata = data.get("metadata") or {}
    raw = metadata.get("order_id") or data.get("client_reference_id")
    try:
        order_id = uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None
    return session.get(PurchaseOrder, order_id)


def _ensure_provisioning_for_order(session: Session, order: PurchaseOrder) -> None:
    if order.clinic_id is None:
        return
    items = list(session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.order_id == order.id)))
    for item in items:
        product = session.get(BillingProduct, item.product_id)
        if product is None or product.code != "phone_number":
            continue
        existing = session.scalar(select(PhoneProvisioningOrder).where(PhoneProvisioningOrder.purchase_order_id == order.id))
        if existing is None:
            session.add(
                PhoneProvisioningOrder(
                    billing_account_id=order.billing_account_id,
                    clinic_id=order.clinic_id,
                    purchase_order_id=order.id,
                    requested_by_user_id=order.created_by_user_id,
                    status="paid_pending_provisioning",
                    quantity=item.quantity,
                )
            )
        upsert_entitlement(
            session,
            clinic_id=order.clinic_id,
            billing_account_id=order.billing_account_id,
            code="phone_number",
            status_value="pending",
            quantity=item.quantity,
            metadata={"purchase_order_id": str(order.id)},
        )
    enqueue_outbox(session, kind="email.send", dedupe_key=f"order-paid:{order.id}", payload={"template": "purchase_confirmed", "order_id": str(order.id)})


def _project_subscription(session: Session, data: dict[str, Any]) -> None:
    stripe_id = str(data.get("id") or "")
    if not stripe_id:
        return
    metadata = data.get("metadata") or {}
    try:
        account_id = uuid.UUID(str(metadata.get("billing_account_id")))
        clinic_id = uuid.UUID(str(metadata.get("clinic_id")))
    except (ValueError, TypeError):
        existing = session.scalar(select(ClinicSubscription).where(ClinicSubscription.stripe_subscription_id == stripe_id))
        if existing is None:
            return
        account_id, clinic_id = existing.billing_account_id, existing.clinic_id
    items = ((data.get("items") or {}).get("data") or [])
    first = items[0] if items else {}
    stripe_item_id = first.get("id")
    quantity = int(first.get("quantity") or 1)
    stripe_price_id = ((first.get("price") or {}).get("id"))
    price = session.scalar(select(BillingPrice).where(BillingPrice.stripe_price_id == stripe_price_id)) if stripe_price_id else None
    row = session.scalar(select(ClinicSubscription).where(ClinicSubscription.stripe_subscription_id == stripe_id))
    if row is None:
        row = ClinicSubscription(
            billing_account_id=account_id,
            clinic_id=clinic_id,
            product_id=price.product_id if price else None,
            price_id=price.id if price else None,
            stripe_subscription_id=stripe_id,
            stripe_subscription_item_id=str(stripe_item_id) if stripe_item_id else None,
            quantity=quantity,
            status=str(data.get("status") or "unknown"),
        )
        session.add(row); session.flush()
    row.status = str(data.get("status") or row.status)
    row.quantity = quantity
    row.current_period_end = _timestamp(data.get("current_period_end"))
    row.cancel_at_period_end = bool(data.get("cancel_at_period_end"))
    row.canceled_at = _timestamp(data.get("canceled_at"))
    row.price_id = price.id if price else row.price_id
    row.product_id = price.product_id if price else row.product_id
    active = row.status in {"active", "trialing"}
    entitlement_status = "cancel_scheduled" if active and row.cancel_at_period_end else ("active" if active else ("past_due" if row.status in {"past_due", "unpaid"} else "inactive"))
    upsert_entitlement(session, clinic_id=clinic_id, billing_account_id=account_id, code="assistant_production", status_value=entitlement_status, quantity=quantity, subscription_id=row.id, starts_at=datetime.now(UTC) if active else None, ends_at=row.current_period_end if row.cancel_at_period_end else None, metadata={"stripe_subscription_id": stripe_id})


def _project_invoice(session: Session, data: dict[str, Any], *, paid: bool) -> None:
    stripe_invoice_id = str(data.get("id") or "")
    customer_id = str(data.get("customer") or "")
    account = session.scalar(select(BillingAccount).where(BillingAccount.stripe_customer_id == customer_id))
    if account is None or not stripe_invoice_id:
        return
    metadata = data.get("metadata") or {}
    try:
        clinic_id = uuid.UUID(str(metadata.get("clinic_id"))) if metadata.get("clinic_id") else None
    except ValueError:
        clinic_id = None
    row = session.scalar(select(PaymentRecord).where(PaymentRecord.stripe_invoice_id == stripe_invoice_id))
    if row is None:
        row = PaymentRecord(
            billing_account_id=account.id,
            clinic_id=clinic_id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_payment_intent_id=str(data.get("payment_intent") or "") or None,
            amount_minor=int(data.get("amount_paid") if paid else data.get("amount_due") or 0),
            currency=str(data.get("currency") or "eur").upper(),
            status="paid" if paid else "failed",
        )
        session.add(row)
    row.status = "paid" if paid else "failed"
    row.paid_at = datetime.now(UTC) if paid else None
    row.failure_code = None if paid else str(data.get("last_finalization_error") or "payment_failed")[:120]
    enqueue_outbox(session, kind="email.send", dedupe_key=f"invoice:{row.status}:{stripe_invoice_id}", payload={"template": "invoice_paid" if paid else "payment_failed", "payment_record_id": str(row.id)})


def _process_event(session: Session, event_type: str, data: dict[str, Any]) -> None:
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        order = _order_from_object(session, data)
        if order is not None:
            paid = event_type.endswith("succeeded") or data.get("payment_status") in {"paid", "no_payment_required"}
            order.status = "paid" if paid else "payment_pending"
            customer_id = str(data.get("customer") or "")
            account = session.get(BillingAccount, order.billing_account_id)
            if account is not None and customer_id:
                account.stripe_customer_id = customer_id
            if paid:
                _ensure_provisioning_for_order(session, order)
    elif event_type == "checkout.session.async_payment_failed":
        order = _order_from_object(session, data)
        if order is not None:
            order.status = "payment_failed"
    elif event_type == "invoice.paid":
        _project_invoice(session, data, paid=True)
    elif event_type == "invoice.payment_failed":
        _project_invoice(session, data, paid=False)
    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        _project_subscription(session, data)
    elif event_type == "charge.refunded":
        intent = str(data.get("payment_intent") or "")
        row = session.scalar(select(PaymentRecord).where(PaymentRecord.stripe_payment_intent_id == intent)) if intent else None
        if row is not None:
            row.status = "refunded"; row.refunded_at = datetime.now(UTC)


@router.post("/api/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, bool]:
    raw = await request.body()
    if len(raw) > settings.max_webhook_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook body is too large.")
    secret = settings.stripe_webhook_secret.get_secret_value().strip()
    if not secret or not stripe_signature:
        raise HTTPException(status_code=503, detail="Stripe webhook verification is not configured.")
    try:
        event = stripe.Webhook.construct_event(raw, stripe_signature, secret)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.") from exc
    event_data = _as_dict(event)
    event_id = str(event_data["id"])
    event_type = str(event_data["type"])
    payload_hash = hashlib.sha256(raw).hexdigest()
    receipt = session.scalar(select(WebhookReceipt).where(WebhookReceipt.provider == "stripe", WebhookReceipt.event_id == event_id))
    if receipt is not None and receipt.status == "completed":
        return {"received": True}
    if receipt is None:
        receipt = WebhookReceipt(provider="stripe", event_id=event_id, event_type=event_type, payload_hash=payload_hash, status="processing", attempts=1)
        session.add(receipt)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return {"received": True}
    else:
        receipt.attempts += 1; receipt.status = "processing"; receipt.last_error = None
    try:
        data = _as_dict(event_data["data"]["object"])
        _process_event(session, event_type, data)
        receipt.status = "completed"; receipt.processed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        receipt = session.scalar(select(WebhookReceipt).where(WebhookReceipt.provider == "stripe", WebhookReceipt.event_id == event_id))
        if receipt is not None:
            receipt.status = "failed"; receipt.last_error = str(exc)[:2000]
            session.commit()
        raise
    return {"received": True}
