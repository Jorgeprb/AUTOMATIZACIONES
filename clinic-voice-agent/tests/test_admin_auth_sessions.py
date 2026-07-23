"""Security regression tests for database-backed administrator sessions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.auth import (
    authenticate_admin,
    create_admin_session,
    ensure_bootstrap_admin,
    principal_from_session,
    revoke_admin_session,
    verify_password,
)
from app.config import Settings


def test_bootstrap_login_session_and_revocation(
    db_session: Session, monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "Tatodobajocontrol")
    settings = Settings()
    user = ensure_bootstrap_admin(db_session, settings)
    assert verify_password("Tatodobajocontrol", user.password_hash)
    authenticated = authenticate_admin(
        db_session, "admin", "Tatodobajocontrol", settings
    )
    assert authenticated is not None
    token, _, record = create_admin_session(
        db_session,
        user=authenticated,
        settings=settings,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    resolved = principal_from_session(db_session, raw_token=token)
    assert resolved is not None
    assert resolved[0].username == "admin"
    assert record.expires_at > datetime.now(UTC)
    revoke_admin_session(db_session, token)
    assert principal_from_session(db_session, raw_token=token) is None


def test_failed_logins_lock_account(db_session: Session, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_LOGIN_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("ADMIN_LOGIN_LOCK_MINUTES", "15")
    settings = Settings()
    user = ensure_bootstrap_admin(db_session, settings)
    assert authenticate_admin(db_session, user.username, "wrong-1", settings) is None
    assert authenticate_admin(db_session, user.username, "wrong-2", settings) is None
    db_session.refresh(user)
    assert user.locked_until is not None
    assert authenticate_admin(
        db_session, user.username, "Tatodobajocontrol", settings
    ) is None
