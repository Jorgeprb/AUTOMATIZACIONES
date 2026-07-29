"""Enterprise registration and Stripe integration tests."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import stripe_webhook as stripe_webhook_api
from app.api.billing import create_checkout
from app.auth import AdminPrincipal
from app.config import Settings, get_settings
from app.db import get_db
from app.enterprise_schemas import CheckoutLine, CheckoutRequest
from app.main import create_app
from app.models import (
    AdminMembership,
    AdminRole,
    AdminUser,
    BillingAccount,
    BillingAccountMember,
    BillingPrice,
    BillingProduct,
    Clinic,
    ClinicEntitlement,
    IntegrationOutbox,
    PhoneProvisioningOrder,
    PurchaseOrder,
    PurchaseOrderItem,
    WebhookReceipt,
)


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return override


def _app(engine: Engine, settings: Settings | None = None) -> FastAPI:
    app = create_app(settings)
    app.dependency_overrides[get_db] = _db_override(_factory(engine))
    return app


@pytest.mark.anyio
async def test_registration_verification_and_multiclinic_onboarding(
    database_engine: Engine,
) -> None:
    settings = get_settings()
    app = _app(database_engine, settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        registered = await client.post(
            "/auth/register",
            json={
                "name": "Clínica Registro",
                "email": "owner@example.test",
                "password": "TestPassword123",
                "repeat_password": "TestPassword123",
                "accepted_terms": True,
                "accepted_privacy": True,
            },
        )
        assert registered.status_code == 201, registered.text
        csrf = client.cookies[settings.admin_csrf_cookie_name]

        with _factory(database_engine)() as session:
            outbox = session.scalar(
                select(IntegrationOutbox).where(
                    IntegrationOutbox.dedupe_key.like("verify-email:%")
                )
            )
            assert outbox is not None
            match = re.search(r"[?&]token=([^\s]+)", str(outbox.payload_json["text"]))
            assert match is not None
            verification_token = match.group(1)

        verified = await client.post(
            "/auth/verify-email",
            json={"token": verification_token},
        )
        repeated = await client.post(
            "/auth/verify-email",
            json={"token": verification_token},
        )
        assert verified.status_code == 204
        assert repeated.status_code == 400

        first = await client.post(
            "/auth/onboarding/clinic",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Clínica Uno",
                "timezone": "Europe/Madrid",
                "main_phone_number": "+34910004001",
            },
        )
        second = await client.post(
            "/auth/onboarding/clinics",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Clínica Dos",
                "timezone": "Europe/Madrid",
                "main_phone_number": "+34910004002",
            },
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

        with _factory(database_engine)() as session:
            foreign = Clinic(
                name="Clínica Ajena",
                timezone="Europe/Madrid",
                main_phone_number="+34910004999",
            )
            session.add(foreign)
            session.commit()
            foreign_id = foreign.id

        cross_tenant = await client.get(f"/api/admin/clinics/{foreign_id}/customers")
        assert cross_tenant.status_code == 403

    with _factory(database_engine)() as session:
        user = session.scalar(
            select(AdminUser).where(AdminUser.email == "owner@example.test")
        )
        assert user is not None and user.email_verified_at is not None
        assert session.scalar(select(func.count(BillingAccount.id))) == 1
        assert (
            session.scalar(
                select(func.count(AdminMembership.id)).where(
                    AdminMembership.user_id == user.id
                )
            )
            == 2
        )


def _commercial_domain(
    session: Session,
) -> tuple[
    AdminUser,
    BillingAccount,
    Clinic,
    BillingProduct,
    BillingPrice,
]:
    user = AdminUser(
        username=f"billing-{uuid.uuid4()}@example.test",
        email=f"billing-{uuid.uuid4()}@example.test",
        display_name="Billing Owner",
        password_hash="disabled-test-hash",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
    )
    session.add(user)
    session.flush()
    account = BillingAccount(
        owner_user_id=user.id,
        display_name="Autogal Test",
        billing_email=user.email or user.username,
        billing_address_json={},
        status="free",
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
    clinic = Clinic(
        billing_account_id=account.id,
        name="Clínica Stripe",
        timezone="Europe/Madrid",
        main_phone_number=f"+3491{uuid.uuid4().int % 10_000_000:08d}",
    )
    product = BillingProduct(
        code="phone_number",
        name="Número",
        product_type="one_time",
        ownership_type="permanent",
        entitlement_code="phone_number",
    )
    session.add_all([clinic, product])
    session.flush()
    session.add(
        AdminMembership(
            user_id=user.id,
            clinic_id=clinic.id,
            role=AdminRole.CLINIC_ADMIN,
        )
    )
    price = BillingPrice(
        product_id=product.id,
        code="phone_number_once",
        currency="EUR",
        unit_amount_minor=1234,
        billing_type="one_time",
        stripe_price_id="price_test_server",
    )
    session.add(price)
    session.commit()
    return user, account, clinic, product, price


def test_checkout_uses_server_catalog_price(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, account, clinic, _product, price = _commercial_domain(db_session)
    account.stripe_customer_id = "cus_test_server"
    db_session.commit()
    captured: dict[str, object] = {}

    def fake_checkout(**kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return {"id": "cs_test_server", "url": "https://checkout.example.test/session"}

    monkeypatch.setattr(
        "app.api.billing.stripe.checkout.Session.create",
        fake_checkout,
    )
    settings = get_settings().model_copy(
        update={"stripe_secret_key": SecretStr("test-only-stripe-key")}
    )
    principal = AdminPrincipal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        avatar_url=None,
        role=AdminRole.CLINIC_ADMIN,
        clinic_ids=frozenset({clinic.id}),
        clinic_roles={clinic.id: AdminRole.CLINIC_ADMIN},
    )
    result = create_checkout(
        CheckoutRequest(
            clinic_id=clinic.id,
            lines=[CheckoutLine(price_id=price.id, quantity=2)],
        ),
        db_session,
        settings,
        principal,
    )

    order = db_session.get(PurchaseOrder, result.order_id)
    assert order is not None
    assert order.total_one_time_minor == 2468
    assert captured["line_items"] == [{"price": "price_test_server", "quantity": 2}]
    assert "unit_amount" not in str(captured["line_items"])


@pytest.mark.anyio
async def test_stripe_paid_webhook_is_idempotent(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _factory(database_engine)
    with factory() as session:
        user, account, clinic, product, price = _commercial_domain(session)
        order = PurchaseOrder(
            billing_account_id=account.id,
            clinic_id=clinic.id,
            created_by_user_id=user.id,
            status="checkout_pending",
            currency="EUR",
            total_one_time_minor=1234,
            total_recurring_minor=0,
        )
        session.add(order)
        session.flush()
        session.add(
            PurchaseOrderItem(
                order_id=order.id,
                product_id=product.id,
                price_id=price.id,
                product_name_snapshot=product.name,
                unit_amount_minor=price.unit_amount_minor,
                quantity=1,
                billing_type="one_time",
                stripe_price_id_snapshot=price.stripe_price_id,
            )
        )
        session.commit()
        order_id = order.id

    event = {
        "id": "evt_test_paid_once",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_paid_once",
                "client_reference_id": str(order_id),
                "payment_status": "paid",
                "customer": "cus_test_paid_once",
                "metadata": {"order_id": str(order_id)},
            }
        },
    }
    monkeypatch.setattr(
        stripe_webhook_api.stripe.Webhook,
        "construct_event",
        lambda _raw, _signature, _secret: event,
    )
    settings = get_settings().model_copy(
        update={"stripe_webhook_secret": SecretStr("test-only-webhook-secret")}
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "test-signature"},
        )
        duplicate = await client.post(
            "/api/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "test-signature"},
        )
        assert first.status_code == 200, first.text
        assert duplicate.status_code == 200, duplicate.text

    with factory() as session:
        order = session.get(PurchaseOrder, order_id)
        receipt = session.scalar(
            select(WebhookReceipt).where(
                WebhookReceipt.event_id == "evt_test_paid_once"
            )
        )
        entitlement = session.scalar(
            select(ClinicEntitlement).where(ClinicEntitlement.code == "phone_number")
        )
        assert order is not None and order.status == "paid"
        assert receipt is not None and receipt.status == "completed"
        assert receipt.attempts == 1
        assert session.scalar(select(func.count(PhoneProvisioningOrder.id))) == 1
        assert entitlement is not None and entitlement.status == "pending"
