"""Database-backed administrator authentication and authorization."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AdminMembership, AdminRole, AdminSession, AdminUser

_PASSWORD_SCHEME = "scrypt"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SESSION_TOKEN_BYTES = 48
_CSRF_TOKEN_BYTES = 32


def _utc_datetime(value: datetime) -> datetime:
    """Normalize database datetimes for safe comparisons across drivers."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    """Authenticated administrator identity attached to a request."""

    user_id: uuid.UUID | None
    username: str
    display_name: str | None
    email: str | None
    avatar_url: str | None
    role: AdminRole
    clinic_ids: frozenset[uuid.UUID]
    clinic_roles: dict[uuid.UUID, AdminRole]
    via_api_key: bool = False

    @property
    def is_super_admin(self) -> bool:
        return self.role == AdminRole.SUPER_ADMIN

    @property
    def can_write(self) -> bool:
        return self.role != AdminRole.READ_ONLY

    def can_access_clinic(self, clinic_id: uuid.UUID) -> bool:
        return self.is_super_admin or clinic_id in self.clinic_ids

    def can_write_clinic(self, clinic_id: uuid.UUID) -> bool:
        if self.is_super_admin:
            return True
        return (
            self.clinic_roles.get(clinic_id, AdminRole.READ_ONLY) != AdminRole.READ_ONLY
        )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Hash a password with stdlib scrypt and an independent random salt."""
    if len(password) < 10:
        raise ValueError("administrator password must contain at least 10 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        (
            _PASSWORD_SCHEME,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            salt.hex(),
            derived.hex(),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password without exposing timing information."""
    try:
        scheme, raw_n, raw_r, raw_p, salt_hex, digest_hex = encoded.split("$", 5)
        if scheme != _PASSWORD_SCHEME:
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), digest_hex)


def ensure_bootstrap_admin(session: Session, settings: Settings) -> AdminUser:
    """Create the first administrator from server-side bootstrap settings."""
    existing = session.scalar(select(AdminUser).order_by(AdminUser.created_at).limit(1))
    if existing is not None:
        return existing
    username = settings.admin_bootstrap_username.strip()
    password = settings.admin_bootstrap_password.get_secret_value()
    user = AdminUser(
        username=username,
        email=username if "@" in username else None,
        display_name="Administrador",
        auth_provider="password",
        password_hash=hash_password(password),
        role=AdminRole.SUPER_ADMIN,
        is_active=True,
        must_change_password=settings.admin_bootstrap_force_password_change,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_admin(
    session: Session, username: str, password: str, settings: Settings
) -> AdminUser | None:
    """Authenticate an active user with persistent brute-force protection."""
    normalized = username.strip()
    if "@" in normalized:
        normalized = normalized.casefold()
    user = session.scalar(
        select(AdminUser)
        .where(
            or_(
                AdminUser.username == normalized,
                AdminUser.email == normalized,
            )
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if user is None or not user.is_active:
        # Keep timing broadly similar even for unknown users.
        hashlib.scrypt(
            password.encode("utf-8"),
            salt=b"autogal-login-pad",
            n=2**12,
            r=8,
            p=1,
            dklen=32,
        )
        return None
    if (
        user.locked_until is not None
        and _utc_datetime(user.locked_until) > now
    ):
        return None
    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.admin_login_max_attempts:
            user.locked_until = now + timedelta(
                minutes=settings.admin_login_lock_minutes
            )
            user.failed_login_count = 0
        session.commit()
        return None
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.commit()
    session.refresh(user)
    return user


def create_admin_session(
    session: Session,
    *,
    user: AdminUser,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str, AdminSession]:
    """Create a revocable opaque browser session and CSRF token."""
    now = datetime.now(UTC)
    session.execute(
        delete(AdminSession).where(
            (AdminSession.expires_at <= now) | (AdminSession.revoked_at.is_not(None))
        )
    )
    raw_token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
    csrf_token = secrets.token_urlsafe(_CSRF_TOKEN_BYTES)
    record = AdminSession(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        csrf_token_hash=_hash_token(csrf_token),
        expires_at=now + timedelta(hours=settings.admin_session_ttl_hours),
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    # SQLite and some legacy drivers can return timezone-naive values even for
    # DateTime(timezone=True). Normalise the in-memory record returned to callers;
    # PostgreSQL values are already aware and remain unchanged.
    record.expires_at = _utc_datetime(record.expires_at)
    if record.revoked_at is not None:
        record.revoked_at = _utc_datetime(record.revoked_at)
    return raw_token, csrf_token, record


def revoke_admin_session(session: Session, raw_token: str | None) -> None:
    """Revoke one browser session if it exists."""
    if not raw_token:
        return
    record = session.scalar(
        select(AdminSession).where(AdminSession.token_hash == _hash_token(raw_token))
    )
    if record is None or record.revoked_at is not None:
        return
    record.revoked_at = datetime.now(UTC)
    session.commit()


def _memberships(session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, AdminRole]:
    return {
        clinic_id: role
        for clinic_id, role in session.execute(
            select(AdminMembership.clinic_id, AdminMembership.role).where(
                AdminMembership.user_id == user_id
            )
        )
    }


def principal_from_session(
    session: Session,
    *,
    raw_token: str,
) -> tuple[AdminPrincipal, AdminSession] | None:
    """Resolve one active opaque session token."""
    now = datetime.now(UTC)
    record = session.scalar(
        select(AdminSession).where(AdminSession.token_hash == _hash_token(raw_token))
    )
    if (
        record is None
        or record.revoked_at is not None
        or _utc_datetime(record.expires_at) <= now
    ):
        return None
    user = session.get(AdminUser, record.user_id)
    if user is None or not user.is_active:
        return None
    memberships = _memberships(session, user.id)
    return (
        AdminPrincipal(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            avatar_url=user.avatar_url,
            role=user.role,
            clinic_ids=frozenset(memberships),
            clinic_roles=memberships,
        ),
        record,
    )


def validate_csrf(request: Request, record: AdminSession, settings: Settings) -> None:
    """Enforce double-submit CSRF on state-changing browser requests."""
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    supplied = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(settings.admin_csrf_cookie_name, "")
    if not supplied or not cookie or not hmac.compare_digest(supplied, cookie):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid CSRF token.",
        )
    if not hmac.compare_digest(_hash_token(supplied), record.csrf_token_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expired or invalid CSRF token.",
        )
