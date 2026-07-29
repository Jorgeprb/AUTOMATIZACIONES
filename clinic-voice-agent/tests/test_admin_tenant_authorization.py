"""Regression coverage for global and tenant administrator boundaries."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import create_admin_session
from app.config import Settings, get_settings
from app.db import get_db
from app.main import create_app
from app.models import AdminMembership, AdminRole, AdminUser, Clinic


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
    app = create_app(settings)
    app.dependency_overrides[get_db] = _db_override(_factory(engine))
    return app


def _browser_session(
    session: Session,
    settings: Settings,
    *,
    role: AdminRole,
    clinic: Clinic | None = None,
) -> tuple[AdminUser, str, str]:
    user = AdminUser(
        username=f"audit-{uuid.uuid4()}@example.test",
        email=f"audit-{uuid.uuid4()}@example.test",
        display_name="Audit user",
        password_hash="!test-only",
        role=role,
        is_active=True,
    )
    session.add(user)
    session.flush()
    if clinic is not None:
        session.add(
            AdminMembership(
                user_id=user.id,
                clinic_id=clinic.id,
                role=role,
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
    return user, raw, csrf


@pytest.mark.anyio
async def test_clinic_admin_cannot_sync_global_voice_catalog(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    factory = _factory(database_engine)
    with factory() as session:
        clinic = Clinic(
            name="Tenant voice clinic",
            timezone="Europe/Madrid",
            main_phone_number="+34910000201",
        )
        session.add(clinic)
        session.commit()
        _user, raw, csrf = _browser_session(
            session,
            settings,
            role=AdminRole.CLINIC_ADMIN,
            clinic=clinic,
        )

    called = False

    def fake_sync(*_args: object) -> dict[str, int]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("app.api.admin.core.sync_voice_catalog", fake_sync)
    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        client.cookies.set(settings.admin_session_cookie_name, raw)
        client.cookies.set(settings.admin_csrf_cookie_name, csrf)
        response = await client.post(
            "/api/admin/voice-providers/sync",
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 403
    assert called is False


@pytest.mark.anyio
async def test_super_admin_cannot_demote_own_account(
    database_engine: Engine,
) -> None:
    settings = get_settings()
    factory = _factory(database_engine)
    with factory() as session:
        user, raw, csrf = _browser_session(
            session,
            settings,
            role=AdminRole.SUPER_ADMIN,
        )
        user_id = user.id

    async with AsyncClient(
        transport=ASGITransport(app=_app(database_engine, settings)),
        base_url="http://testserver",
    ) as client:
        client.cookies.set(settings.admin_session_cookie_name, raw)
        client.cookies.set(settings.admin_csrf_cookie_name, csrf)
        response = await client.patch(
            f"/api/admin/users/{user_id}",
            json={"role": AdminRole.CLINIC_ADMIN.value},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 422
    with factory() as session:
        persisted = session.get(AdminUser, user_id)
        assert persisted is not None
        assert persisted.role is AdminRole.SUPER_ADMIN
