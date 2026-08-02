"""Regression coverage for the August 2026 client/admin workflow fixes."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.admin_schemas import WorkerCreate, WorkerUpdate
from app.api.admin.activity import _call_analysis, _redact_value, list_calls
from app.api.admin.core import (
    create_worker,
    delete_assistant_config,
    delete_worker,
    list_workers,
    update_worker,
)
from app.api.admin.enterprise import delete_customer, update_provisioning
from app.api.admin.overview import get_dashboard
from app.api.billing import create_checkout
from app.api.calendar import list_calendars
from app.auth import AdminPrincipal
from app.config import Settings
from app.db import get_db
from app.enterprise_schemas import CheckoutLine, CheckoutRequest, ProvisioningUpdate
from app.enterprise_service import portal_access_state_for_account
from app.main import create_app
from app.models import (
    AdminMembership,
    AdminRole,
    AdminUser,
    AssistantConfig,
    BillingAccount,
    BillingAccountMember,
    BillingPrice,
    BillingProduct,
    CallSession,
    CallStatus,
    Clinic,
    ClinicCustomer,
    IntegrationOutbox,
    PhoneNumber,
    PhoneProvisioningOrder,
    PurchaseOrder,
    PurchaseOrderItem,
    Worker,
)
from app.calendar.google_client import GoogleAuthorizationRequired, GoogleCalendarError
from app.utils.security import _enforce_client_portal_unlock


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _db_override(
    factory: sessionmaker[Session],
) -> Callable[[], Generator[Session, None, None]]:
    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return override


def _app(engine: Engine, settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_db] = _db_override(_factory(engine))
    return application


def _tenant(db_session: Session, *, with_clinic: bool = True):
    email = f"owner-{uuid.uuid4()}@example.test"
    user = AdminUser(
        username=email,
        email=email,
        display_name="Owner",
        password_hash="!test-only",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    account = BillingAccount(
        owner_user_id=user.id,
        display_name="Cuenta prueba",
        billing_email=email,
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
    clinic = None
    if with_clinic:
        clinic = Clinic(
            billing_account_id=account.id,
            name="Clínica prueba",
            timezone="Europe/Madrid",
            default_language="es",
            main_phone_number=f"pending-{uuid.uuid4().hex}",
            is_active=True,
        )
        db_session.add(clinic)
        db_session.flush()
        db_session.add(
            AdminMembership(
                user_id=user.id,
                clinic_id=clinic.id,
                role=AdminRole.CLINIC_ADMIN,
            )
        )
    db_session.flush()
    principal = AdminPrincipal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        avatar_url=None,
        role=AdminRole.CLINIC_ADMIN,
        clinic_ids=frozenset({clinic.id} if clinic else set()),
        clinic_roles={clinic.id: AdminRole.CLINIC_ADMIN} if clinic else {},
    )
    return user, account, clinic, principal


@pytest.mark.anyio
async def test_registration_creates_browser_session_and_survives_no_clinic_navigation(
    database_engine: Engine,
) -> None:
    settings = Settings().model_copy(
        update={
            "registration_enabled": True,
            "admin_secure_cookies": False,
            "auth_cookie_domain": "",
        }
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://client.autogal.test",
    ) as client:
        registered = await client.post(
            "/auth/register",
            json={
                "name": "Nova clienta",
                "email": f"new-{uuid.uuid4()}@example.test",
                "password": "StrongPassword123",
                "repeat_password": "StrongPassword123",
                "accepted_terms": True,
                "accepted_privacy": True,
            },
        )
        assert registered.status_code == 201
        assert settings.admin_session_cookie_name in client.cookies
        assert settings.admin_csrf_cookie_name in client.cookies

        identity = await client.get("/auth/me")
        clinics = await client.get("/api/admin/clinics")
        billing = await client.get("/api/billing/summary")

    assert identity.status_code == 200
    assert identity.json()["clinic_ids"] == []
    assert clinics.status_code == 200
    assert clinics.json()["items"] == []
    assert billing.status_code == 200
    assert billing.json()["account"] is not None


def test_one_time_checkout_without_clinic_uses_server_catalog_price(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, account, _, principal = _tenant(db_session, with_clinic=False)
    product = BillingProduct(
        code="phone_number",
        name="Número de teléfono Autogal",
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
        stripe_price_id="price_phone_test",
        is_active=True,
    )
    db_session.add(price)
    db_session.commit()

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.api.billing.stripe.Customer.create",
        lambda **_kwargs: {"id": "cus_test"},
    )

    def checkout_create(**kwargs):
        captured.update(kwargs)
        return {"id": "cs_test", "url": "https://checkout.test/session"}

    monkeypatch.setattr("app.api.billing.stripe.checkout.Session.create", checkout_create)
    settings = Settings().model_copy(
        update={"stripe_secret_key": SecretStr("sk_test_123")}
    )
    result = create_checkout(
        CheckoutRequest(
            clinic_id=None,
            lines=[CheckoutLine(price_id=price.id, quantity=2)],
        ),
        db_session,
        settings,
        principal,
    )

    order = db_session.get(PurchaseOrder, result.order_id)
    assert order is not None
    assert order.clinic_id is None
    assert order.total_one_time_minor == 3000
    assert order.total_recurring_minor == 0
    assert captured["mode"] == "payment"
    assert captured["line_items"] == [{"price": "price_phone_test", "quantity": 2}]
    assert "clinic_id" not in captured["metadata"]
    assert account.stripe_customer_id == "cus_test"


def test_recurring_checkout_requires_real_clinic(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, principal = _tenant(db_session, with_clinic=False)
    product = BillingProduct(
        code="monthly_service",
        name="Servicio mensual",
        product_type="subscription",
        ownership_type="license",
        entitlement_code="assistant_production",
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    price = BillingPrice(
        product_id=product.id,
        code="monthly_service",
        currency="EUR",
        unit_amount_minor=5000,
        billing_type="recurring",
        interval="month",
        stripe_price_id="price_monthly_test",
        is_active=True,
    )
    db_session.add(price)
    db_session.commit()
    settings = Settings().model_copy(
        update={"stripe_secret_key": SecretStr("sk_test_123")}
    )
    with pytest.raises(HTTPException) as exc:
        create_checkout(
            CheckoutRequest(
                clinic_id=None,
                lines=[CheckoutLine(price_id=price.id, quantity=1)],
            ),
            db_session,
            settings,
            principal,
        )
    assert exc.value.status_code == 422


def test_admin_assignment_unlocks_account_without_stripe_purchase(
    db_session: Session,
) -> None:
    user, account, clinic, client_principal = _tenant(db_session)
    assert clinic is not None
    provisioning = PhoneProvisioningOrder(
        billing_account_id=account.id,
        clinic_id=None,
        requested_by_user_id=user.id,
        status="paid_pending_provisioning",
        quantity=1,
    )
    db_session.add(provisioning)
    db_session.commit()
    assert portal_access_state_for_account(db_session, account.id).unlocked is False

    super_principal = AdminPrincipal(
        user_id=uuid.uuid4(),
        username="admin",
        display_name="Admin",
        email="admin@example.test",
        avatar_url=None,
        role=AdminRole.SUPER_ADMIN,
        clinic_ids=frozenset(),
        clinic_roles={},
    )
    update_provisioning(
        provisioning.id,
        ProvisioningUpdate(
            clinic_id=clinic.id,
            assigned_number="+34881179999",
            provider="voip_studio",
            sip_target="sip:test@example.test",
            status="active",
        ),
        db_session,
        super_principal,
    )

    state = portal_access_state_for_account(db_session, account.id)
    assert state.unlocked is True
    assert clinic.id in state.assigned_phone_clinic_ids
    phone = db_session.scalar(
        select(PhoneNumber).where(PhoneNumber.phone_number == "+34881179999")
    )
    assert phone is not None and phone.clinic_id == clinic.id and phone.is_active
    assert db_session.scalar(
        select(IntegrationOutbox).where(
            IntegrationOutbox.dedupe_key == f"number-active:{provisioning.id}"
        )
    ) is not None

    request = Request(
        {
            "type": "http",
            "path": f"/api/admin/clinics/{clinic.id}/customers",
            "method": "GET",
            "headers": [(b"host", b"voice.autogal.es")],
        }
    )
    _enforce_client_portal_unlock(request, client_principal, db_session, object())



def test_dashboard_handles_partial_and_active_phone_records(db_session: Session) -> None:
    _, _, clinic, _ = _tenant(db_session)
    assert clinic is not None
    partial = PhoneNumber(
        clinic_id=clinic.id,
        provider="other",
        phone_number="+34881170088",
        label="Número asignado",
        sip_target=None,
        webhook_url=None,
        is_active=True,
    )
    historical = CallSession(
        clinic_id=clinic.id,
        phone_number_id=None,
        assistant_config_id=None,
        openai_call_id=f"historical-dashboard-{uuid.uuid4()}",
        caller_phone="",
        called_number="",
        status=CallStatus.FAILED,
        started_at=None,
    )
    db_session.add_all([partial, historical])
    db_session.commit()

    dashboard = get_dashboard(clinic.id, db_session)

    assert dashboard.clinic_id == clinic.id
    assert dashboard.phone_number_configured is False
    assert dashboard.last_call is not None
    assert dashboard.last_call.caller_phone == "desconocido"
    assert dashboard.last_call.called_number == "desconocido"

    partial.sip_target = "sip:bot@example.test"
    db_session.commit()
    dashboard = get_dashboard(clinic.id, db_session)
    assert dashboard.phone_number_configured is True

def test_workers_support_empty_inherited_custom_and_safe_delete(db_session: Session) -> None:
    _, _, clinic, _ = _tenant(db_session)
    assert clinic is not None
    empty = list_workers(clinic.id, db_session, page=1, page_size=20, is_active=None)
    assert empty.items == []

    inherited = create_worker(
        clinic.id,
        WorkerCreate(name="Ana", role="Peluquera", inherit_clinic_hours=True),
        db_session,
    )
    assert inherited.inherit_clinic_hours is True
    custom_hours = {"monday": [{"start": "10:00", "end": "18:00"}]}
    updated = update_worker(
        clinic.id,
        inherited.id,
        WorkerUpdate(
            inherit_clinic_hours=False,
            working_hours_json=custom_hours,
        ),
        db_session,
    )
    assert updated.inherit_clinic_hours is False
    assert updated.working_hours_json == custom_hours
    deleted = delete_worker(clinic.id, inherited.id, db_session)
    assert deleted.id == inherited.id


def test_delete_active_assistant_config_activates_replacement_and_is_tenant_scoped(
    db_session: Session,
) -> None:
    if db_session.bind is not None and db_session.bind.dialect.name != "postgresql":
        pytest.skip("The active-config partial unique index requires PostgreSQL.")
    _, _, clinic, _ = _tenant(db_session)
    assert clinic is not None
    other = Clinic(
        name="Otra clínica",
        timezone="Europe/Madrid",
        main_phone_number=f"pending-{uuid.uuid4().hex}",
    )
    db_session.add(other)
    db_session.flush()
    active = AssistantConfig(
        clinic_id=clinic.id,
        name="Activa",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es",
        first_message="Hola",
        system_prompt="Ayuda.",
        safety_prompt="Seguridad.",
        booking_policy_prompt="Reserva.",
        cancellation_policy_prompt="Cancela.",
        transfer_policy_prompt="Transfiere.",
        is_active=True,
    )
    replacement = AssistantConfig(
        clinic_id=clinic.id,
        name="Reemplazo",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es",
        first_message="Hola",
        system_prompt="Ayuda.",
        safety_prompt="Seguridad.",
        booking_policy_prompt="Reserva.",
        cancellation_policy_prompt="Cancela.",
        transfer_policy_prompt="Transfiere.",
        is_active=False,
    )
    foreign = AssistantConfig(
        clinic_id=other.id,
        name="Ajena",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es",
        first_message="Hola",
        system_prompt="Ayuda.",
        safety_prompt="Seguridad.",
        booking_policy_prompt="Reserva.",
        cancellation_policy_prompt="Cancela.",
        transfer_policy_prompt="Transfiere.",
        is_active=True,
    )
    db_session.add_all([active, replacement, foreign])
    db_session.commit()

    result = delete_assistant_config(clinic.id, active.id, db_session)
    assert result.id == active.id
    assert db_session.get(AssistantConfig, active.id) is None
    assert db_session.get(AssistantConfig, replacement.id).is_active is True
    with pytest.raises(HTTPException) as exc:
        delete_assistant_config(clinic.id, foreign.id, db_session)
    assert exc.value.status_code == 404


def test_conversations_handle_empty_optional_relations_and_empty_redaction(
    db_session: Session,
) -> None:
    _, _, clinic, _ = _tenant(db_session)
    assert clinic is not None
    call = CallSession(
        clinic_id=clinic.id,
        phone_number_id=None,
        assistant_config_id=None,
        customer_id=None,
        openai_call_id=f"historical-{uuid.uuid4()}",
        caller_phone="desconocido",
        called_number="desconocido",
        status=CallStatus.FAILED,
        conversation_state_json={},
        transcript_text=None,
    )
    db_session.add(call)
    db_session.commit()
    page = list_calls(
        clinic.id,
        db_session,
        page=1,
        page_size=20,
        active=None,
        call_date=None,
        date_from=None,
        date_to=None,
        outcome=None,
        status_filter=None,
        phone=None,
        worker_id=None,
        service_id=None,
    )
    assert page.total == 1
    assert page.items[0].appointment is None
    assert page.items[0].phone_number_id is None
    assert page.items[0].assistant_config_id is None
    assert _redact_value("abc", "") == "abc"
    assert _call_analysis(call).duration_seconds is None


def test_calendar_dependency_errors_do_not_invalidate_portal_session(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, clinic, _ = _tenant(db_session)
    assert clinic is not None
    settings = Settings()

    monkeypatch.setattr(
        "app.api.calendar.get_authorized_calendar_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            GoogleAuthorizationRequired("Conecta Google Calendar.")
        ),
    )
    with pytest.raises(HTTPException) as authorization:
        list_calendars(clinic.id, db_session, settings)
    assert authorization.value.status_code == 428

    monkeypatch.setattr(
        "app.api.calendar.get_authorized_calendar_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            GoogleCalendarError("Google no está disponible.")
        ),
    )
    with pytest.raises(HTTPException) as dependency:
        list_calendars(clinic.id, db_session, settings)
    assert dependency.value.status_code == 424


def test_customer_delete_is_physical_without_history_and_anonymized_with_history(
    db_session: Session,
) -> None:
    _, _, clinic, _ = _tenant(db_session)
    assert clinic is not None
    disposable = ClinicCustomer(
        clinic_id=clinic.id,
        name="Eliminar",
        normalized_phone="+34881170001",
        display_phone="+34 881 170 001",
        custom_values_json={},
        personalization_enabled=True,
        is_active=True,
    )
    historical = ClinicCustomer(
        clinic_id=clinic.id,
        name="Con historial",
        normalized_phone="+34881170002",
        display_phone="+34 881 170 002",
        custom_values_json={},
        personalization_enabled=True,
        is_active=True,
    )
    db_session.add_all([disposable, historical])
    db_session.flush()
    call = CallSession(
        clinic_id=clinic.id,
        customer_id=historical.id,
        openai_call_id=f"customer-history-{uuid.uuid4()}",
        caller_phone=historical.normalized_phone,
        caller_name=historical.name,
        called_number="+34881170999",
        status=CallStatus.COMPLETED,
    )
    db_session.add(call)
    db_session.commit()

    delete_customer(clinic.id, disposable.id, db_session)
    assert db_session.get(ClinicCustomer, disposable.id) is None

    delete_customer(clinic.id, historical.id, db_session)
    stored = db_session.get(ClinicCustomer, historical.id)
    assert stored is not None
    assert stored.is_active is False
    assert stored.name == "Cliente anonimizado"
    assert stored.anonymized_at is not None
    persisted_call = db_session.get(CallSession, call.id)
    assert persisted_call is not None
    assert persisted_call.caller_name == "Con historial"
    assert persisted_call.caller_phone == "+34881170002"
