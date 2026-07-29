"""Focused security regressions found by the final Enterprise audit."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import realtime_preview as preview_service
from app.api import stripe_webhook as stripe_webhook_api
from app.auth import (
    authenticate_admin,
    create_admin_session,
    hash_password,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.enterprise_schemas import PasswordResetRequest
from app.enterprise_service import consume_action_token, create_action_token
from app.main import create_app
from app.models import (
    AdminMembership,
    AdminRole,
    AdminUser,
    AssistantConfig,
    AuthActionToken,
    BillingAccount,
    CallSession,
    CallStatus,
    Clinic,
    ClinicEntitlement,
    ClinicSubscription,
    WebhookReceipt,
)
from app.models import (
    TestSession as SessionRecord,
)
from app.realtime_preview import RealtimePreviewRegistryEntry


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


def _browser_user(
    session: Session,
    settings: Settings,
    *,
    clinic: Clinic,
) -> tuple[str, str]:
    user = AdminUser(
        username=f"tenant-{uuid.uuid4()}@example.test",
        email=f"tenant-{uuid.uuid4()}@example.test",
        display_name="Tenant user",
        password_hash="!test-only",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(
        AdminMembership(
            user_id=user.id,
            clinic_id=clinic.id,
            role=AdminRole.CLINIC_ADMIN,
        )
    )
    session.commit()
    raw, csrf, _ = create_admin_session(
        session,
        user=user,
        settings=settings,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    return raw, csrf


def _two_clinics_with_foreign_sessions(
    session: Session,
) -> tuple[Clinic, Clinic, SessionRecord, RealtimePreviewRegistryEntry]:
    owner = Clinic(
        name="Owner clinic",
        timezone="Europe/Madrid",
        main_phone_number="+34910000101",
    )
    foreign = Clinic(
        name="Foreign clinic",
        timezone="Europe/Madrid",
        main_phone_number="+34910000102",
    )
    config = AssistantConfig(
        clinic=owner,
        name="Owner assistant",
        realtime_model="gpt-realtime-2",
        realtime_voice="marin",
        language="es",
        first_message="Hola",
        system_prompt="Ayuda.",
        safety_prompt="No diagnostiques.",
        booking_policy_prompt="Confirma la reserva.",
        cancellation_policy_prompt="Confirma la cancelación.",
        transfer_policy_prompt="Transfiere si es necesario.",
        is_active=True,
    )
    session.add_all([owner, foreign, config])
    session.flush()
    test_session = SessionRecord(
        clinic_id=owner.id,
        assistant_config_id=config.id,
        messages_json=[],
        state_json={},
    )
    call = CallSession(
        clinic_id=owner.id,
        assistant_config_id=config.id,
        openai_call_id=f"preview-audit-{uuid.uuid4()}",
        caller_phone="browser-preview",
        called_number="browser-preview",
        status=CallStatus.ACTIVE,
    )
    session.add_all([test_session, call])
    session.commit()
    preview = RealtimePreviewRegistryEntry(
        id=uuid.uuid4(),
        clinic_id=owner.id,
        call_session_id=call.id,
        model="gpt-realtime-2",
        voice="marin",
        call_audio_mode="openai_hosted_sip",
        voice_provider="openai",
        expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    preview_service._REGISTRY[preview.id] = preview
    return owner, foreign, test_session, preview


@pytest.mark.anyio
async def test_child_sessions_reject_cross_tenant_access(
    database_engine: Engine,
) -> None:
    settings = get_settings()
    factory = _factory(database_engine)
    with factory() as session:
        _owner, foreign, test_session, preview = _two_clinics_with_foreign_sessions(
            session
        )
        raw, csrf = _browser_user(session, settings, clinic=foreign)
        test_session_id = test_session.id
        preview_id = preview.id

    app = _app(database_engine, settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            client.cookies.set(settings.admin_session_cookie_name, raw)
            client.cookies.set(settings.admin_csrf_cookie_name, csrf)
            read = await client.get(f"/api/admin/test-sessions/{test_session_id}")
            heartbeat = await client.post(
                f"/api/admin/realtime-preview-sessions/{preview_id}/heartbeat",
                headers={"X-CSRF-Token": csrf},
            )
        assert read.status_code == 403
        assert heartbeat.status_code == 403
    finally:
        preview_service._REGISTRY.pop(preview_id, None)


@pytest.mark.anyio
async def test_google_calendar_oauth_start_requires_authentication(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _factory(database_engine)() as session:
        clinic = Clinic(
            name="OAuth clinic",
            timezone="Europe/Madrid",
            main_phone_number="+34910000103",
        )
        session.add(clinic)
        session.commit()
        clinic_id = clinic.id
    monkeypatch.setattr(
        "app.api.google_auth.create_google_authorization_request",
        lambda *_args: pytest.fail("OAuth must not start before authentication"),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine)),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/auth/google/start?clinic_id={clinic_id}", follow_redirects=False
        )
    assert response.status_code == 401


def test_email_login_is_case_insensitive(db_session: Session) -> None:
    settings = get_settings()
    password = "CaseLogin123"
    user = AdminUser(
        username="case-owner@example.test",
        email="case-owner@example.test",
        password_hash=hash_password(password),
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    authenticated = authenticate_admin(
        db_session, "CASE-OWNER@EXAMPLE.TEST", password, settings
    )
    assert authenticated is not None
    assert authenticated.id == user.id


def test_concurrent_failed_logins_cannot_lose_lockout_updates(
    database_engine: Engine,
) -> None:
    if database_engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL.")
    factory = _factory(database_engine)
    settings = get_settings().model_copy(
        update={"admin_login_max_attempts": 2, "admin_login_lock_minutes": 15}
    )
    with factory() as session:
        user = AdminUser(
            username="concurrent-login@example.test",
            email="concurrent-login@example.test",
            password_hash=hash_password("CorrectPassword123"),
            role=AdminRole.CLINIC_ADMIN,
            is_active=True,
        )
        session.add(user)
        session.commit()
        user_id = user.id

    from threading import Barrier

    barrier = Barrier(2)

    def synchronize_select(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "FROM admin_users" in statement and "admin_users.username" in statement:
            barrier.wait(timeout=5)

    def fail_login() -> None:
        with factory() as session:
            assert authenticate_admin(
                session, "concurrent-login@example.test", "wrong-password", settings
            ) is None

    event.listen(database_engine, "before_cursor_execute", synchronize_select)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(fail_login) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)
    finally:
        event.remove(database_engine, "before_cursor_execute", synchronize_select)

    with factory() as session:
        user = session.get(AdminUser, user_id)
        assert user is not None
        assert user.locked_until is not None
        assert user.failed_login_count == 0


def test_password_reset_keeps_registration_password_policy() -> None:
    with pytest.raises(ValidationError):
        PasswordResetRequest(
            token="x" * 48,
            password="alllowercase1",
            repeat_password="alllowercase1",
        )


def test_action_token_is_consumed_once_under_concurrency(
    database_engine: Engine,
) -> None:
    if database_engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL.")
    factory = _factory(database_engine)
    with factory() as setup:
        user = AdminUser(
            username=f"token-{uuid.uuid4()}@example.test",
            email=f"token-{uuid.uuid4()}@example.test",
            password_hash="!test-only",
            role=AdminRole.CLINIC_ADMIN,
            is_active=True,
        )
        setup.add(user)
        setup.flush()
        raw = create_action_token(
            setup,
            user_id=user.id,
            kind="reset_password",
            ttl=timedelta(minutes=10),
        )
        setup.commit()

    first = factory()
    try:
        first_result = consume_action_token(first, raw_token=raw, kind="reset_password")
        assert first_result is not None

        def consume_second() -> bool:
            with factory() as second:
                result = consume_action_token(
                    second, raw_token=raw, kind="reset_password"
                )
                second.commit()
                return result is not None

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(consume_second)
            # Without a row lock the second transaction consumes immediately.
            time.sleep(0.2)
            first.commit()
            second_consumed = future.result(timeout=5)
        assert second_consumed is False
    finally:
        first.close()

    with factory() as verification:
        row = verification.scalar(select(AuthActionToken))
        assert row is not None and row.used_at is not None


def test_consuming_password_reset_invalidates_other_active_links(
    database_engine: Engine,
) -> None:
    factory = _factory(database_engine)
    with factory() as session:
        user = AdminUser(
            username=f"reset-{uuid.uuid4()}@example.test",
            email=f"reset-{uuid.uuid4()}@example.test",
            password_hash="!test-only",
            role=AdminRole.CLINIC_ADMIN,
            is_active=True,
        )
        session.add(user)
        session.flush()
        older = create_action_token(
            session,
            user_id=user.id,
            kind="reset_password",
            ttl=timedelta(minutes=10),
        )
        newer = create_action_token(
            session,
            user_id=user.id,
            kind="reset_password",
            ttl=timedelta(minutes=10),
        )
        session.commit()

    with factory() as session:
        assert (
            consume_action_token(session, raw_token=newer, kind="reset_password")
            is not None
        )
        session.commit()
    with factory() as session:
        assert (
            consume_action_token(session, raw_token=older, kind="reset_password")
            is None
        )


def _billing_tenant(session: Session, label: str) -> tuple[BillingAccount, Clinic]:
    user = AdminUser(
        username=f"billing-{label}-{uuid.uuid4()}@example.test",
        email=f"billing-{label}-{uuid.uuid4()}@example.test",
        password_hash="!test-only",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
    )
    session.add(user)
    session.flush()
    account = BillingAccount(
        owner_user_id=user.id,
        display_name=f"Account {label}",
        billing_email=user.email or user.username,
        stripe_customer_id=f"cus_{label}_{uuid.uuid4().hex}",
        billing_address_json={},
        status="free",
    )
    session.add(account)
    session.flush()
    clinic = Clinic(
        billing_account_id=account.id,
        name=f"Clinic {label}",
        timezone="Europe/Madrid",
        main_phone_number=f"+349{uuid.uuid4().int % 10_000_000_000:010d}",
    )
    session.add(clinic)
    session.flush()
    return account, clinic


def test_subscription_does_not_activate_before_confirmed_payment(
    db_session: Session,
) -> None:
    account, clinic = _billing_tenant(db_session, "pending")
    stripe_webhook_api._process_event(
        db_session,
        "customer.subscription.created",
        {
            "id": "sub_pending_without_payment",
            "status": "active",
            "metadata": {
                "billing_account_id": str(account.id),
                "clinic_id": str(clinic.id),
            },
            "items": {"data": []},
        },
    )
    db_session.flush()
    entitlement = db_session.scalar(
        select(ClinicEntitlement).where(
            ClinicEntitlement.clinic_id == clinic.id,
            ClinicEntitlement.code == "assistant_production",
        )
    )
    assert entitlement is not None
    assert entitlement.status == "pending_payment"


def test_paid_invoice_activates_existing_subscription_entitlement(
    db_session: Session,
) -> None:
    account, clinic = _billing_tenant(db_session, "invoice")
    subscription = ClinicSubscription(
        billing_account_id=account.id,
        clinic_id=clinic.id,
        stripe_subscription_id="sub_invoice_paid",
        status="active",
    )
    db_session.add(subscription)
    db_session.flush()
    entitlement = ClinicEntitlement(
        billing_account_id=account.id,
        clinic_id=clinic.id,
        subscription_id=subscription.id,
        code="assistant_production",
        status="pending_payment",
        quantity=1,
        metadata_json={},
    )
    db_session.add(entitlement)
    db_session.flush()
    stripe_webhook_api._process_event(
        db_session,
        "invoice.paid",
        {
            "id": "in_subscription_paid",
            "customer": account.stripe_customer_id,
            "subscription": subscription.stripe_subscription_id,
            "amount_paid": 4900,
            "currency": "eur",
        },
    )
    db_session.flush()
    assert entitlement.status == "active"


def test_subscription_metadata_cannot_move_entitlement_across_tenants(
    db_session: Session,
) -> None:
    owner_account, owner_clinic = _billing_tenant(db_session, "owner")
    foreign_account, foreign_clinic = _billing_tenant(db_session, "foreign")
    subscription = ClinicSubscription(
        billing_account_id=owner_account.id,
        clinic_id=owner_clinic.id,
        stripe_subscription_id="sub_tenant_metadata",
        status="active",
    )
    db_session.add(subscription)
    db_session.flush()
    stripe_webhook_api._process_event(
        db_session,
        "customer.subscription.updated",
        {
            "id": subscription.stripe_subscription_id,
            "status": "active",
            "metadata": {
                "billing_account_id": str(foreign_account.id),
                "clinic_id": str(foreign_clinic.id),
            },
            "items": {"data": []},
        },
    )
    db_session.flush()
    leaked = db_session.scalar(
        select(ClinicEntitlement).where(
            ClinicEntitlement.clinic_id == foreign_clinic.id,
            ClinicEntitlement.code == "assistant_production",
        )
    )
    assert leaked is None


@pytest.mark.anyio
async def test_failed_stripe_webhook_persists_attempt_and_retries(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = {
        "id": "evt_audit_transient_failure",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_audit", "payment_status": "paid"}},
    }
    monkeypatch.setattr(
        stripe_webhook_api.stripe.Webhook,
        "construct_event",
        lambda *_args: event,
    )
    calls = 0

    def transient_failure(*_args: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("test-only transient failure")

    monkeypatch.setattr(stripe_webhook_api, "_process_event", transient_failure)
    settings = get_settings().model_copy(
        update={"stripe_webhook_secret": SecretStr("test-only-webhook-secret")}
    )
    app = _app(database_engine, settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        with pytest.raises(RuntimeError, match="test-only transient failure"):
            await client.post(
                "/api/webhooks/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "test-signature"},
            )
        with _factory(database_engine)() as session:
            failed = session.scalar(
                select(WebhookReceipt).where(
                    WebhookReceipt.event_id == "evt_audit_transient_failure"
                )
            )
            assert failed is not None
            assert failed.status == "failed"
            assert failed.attempts == 1

        retry = await client.post(
            "/api/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "test-signature"},
        )
        assert retry.status_code == 200

    with _factory(database_engine)() as session:
        completed = session.scalar(
            select(WebhookReceipt).where(
                WebhookReceipt.event_id == "evt_audit_transient_failure"
            )
        )
        assert completed is not None
        assert completed.status == "completed"
        assert completed.attempts == 2
