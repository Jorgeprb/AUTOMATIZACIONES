"""Browser authentication for the administration and client portals."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.auth import (
    AdminPrincipal,
    authenticate_admin,
    create_admin_session,
    revoke_admin_session,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.enterprise_service import create_billing_account_for_user
from app.models import AdminMembership, AdminRole, AdminUser, OAuthLoginState
from app.utils.security import require_admin_access

router = APIRouter(prefix="/auth", tags=["portal-auth"])
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=1024)


class AdminIdentity(BaseModel):
    user_id: str | None = None
    username: str
    display_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    role: str
    clinic_ids: list[str]
    must_change_password: bool = False
    is_super_admin: bool = False


def _secure_cookie(settings: Settings) -> bool:
    return settings.app_environment == "production" or settings.admin_secure_cookies


def _cookie_domain(settings: Settings) -> str | None:
    value = settings.auth_cookie_domain.strip()
    return value or None


def _set_session_cookies(
    response: Response,
    *,
    raw_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    max_age = settings.admin_session_ttl_hours * 3600
    response.set_cookie(
        settings.admin_session_cookie_name,
        raw_token,
        httponly=True,
        max_age=max_age,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
        domain=_cookie_domain(settings),
    )
    response.set_cookie(
        settings.admin_csrf_cookie_name,
        csrf_token,
        httponly=False,
        max_age=max_age,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
        domain=_cookie_domain(settings),
    )


def _identity_for_user(session: Session, user: AdminUser) -> AdminIdentity:
    clinic_ids = list(
        session.scalars(
            select(AdminMembership.clinic_id).where(AdminMembership.user_id == user.id)
        )
    )
    return AdminIdentity(
        user_id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        email=user.email or user.username,
        avatar_url=user.avatar_url,
        role=user.role.value,
        clinic_ids=[str(item) for item in sorted(clinic_ids, key=str)],
        must_change_password=user.must_change_password,
        is_super_admin=user.role == AdminRole.SUPER_ADMIN,
    )


def _safe_return_to(value: str | None) -> str:
    candidate = (value or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate[:1000]


def _portal_base(settings: Settings, portal: str, user: AdminUser | None = None) -> str:
    if user is not None and user.role == AdminRole.SUPER_ADMIN:
        return settings.admin_frontend_base_url.rstrip("/")
    if portal == "admin":
        return settings.admin_frontend_base_url.rstrip("/")
    return settings.client_frontend_base_url.rstrip("/")


def _login_redirect_uri(settings: Settings, portal: str) -> str:
    if portal == "admin":
        return settings.google_login_admin_redirect_uri
    return settings.google_login_client_redirect_uri


def _oauth_error_redirect(
    settings: Settings,
    *,
    portal: str,
    code: str,
) -> RedirectResponse:
    base = _portal_base(settings, portal)
    return RedirectResponse(
        f"{base}/login?{urlencode({'auth_error': code})}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/login", response_model=AdminIdentity)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminIdentity:
    """Authenticate with password and issue a revocable server-side session."""
    user = authenticate_admin(session, payload.username, payload.password, settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )
    raw_token, csrf_token, _ = create_admin_session(
        session,
        user=user,
        settings=settings,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    _set_session_cookies(
        response,
        raw_token=raw_token,
        csrf_token=csrf_token,
        settings=settings,
    )
    return _identity_for_user(session, user)


@router.get("/login/google/start", response_class=RedirectResponse)
def start_google_login(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    portal: Annotated[Literal["admin", "client"], Query()] = "client",
    return_to: Annotated[str | None, Query()] = "/",
) -> RedirectResponse:
    """Start Google OpenID Connect login with state, nonce, and PKCE."""
    if not settings.google_login_enabled:
        raise HTTPException(status_code=404, detail="Google login is disabled.")
    redirect_uri = _login_redirect_uri(settings, portal)
    if not redirect_uri:
        raise HTTPException(status_code=503, detail="Google login is not configured.")

    now = datetime.now(UTC)
    session.execute(delete(OAuthLoginState).where(OAuthLoginState.expires_at <= now))
    state = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    session.add(
        OAuthLoginState(
            state_hash=hashlib.sha256(state.encode("utf-8")).hexdigest(),
            nonce=nonce,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            portal=portal,
            return_to=_safe_return_to(return_to),
            expires_at=now + timedelta(minutes=10),
        )
    )
    session.commit()
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return RedirectResponse(f"{_GOOGLE_AUTH_URL}?{query}", status_code=302)


@router.get("/login/google/callback", response_class=RedirectResponse)
def complete_google_login(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    state_value: Annotated[str | None, Query(alias="state")] = None,
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Complete Google login and redirect to the correct portal."""
    if not state_value:
        return _oauth_error_redirect(settings, portal="client", code="missing_state")
    state_hash = hashlib.sha256(state_value.encode("utf-8")).hexdigest()
    transaction = session.scalar(
        select(OAuthLoginState).where(OAuthLoginState.state_hash == state_hash)
    )
    if transaction is None or transaction.expires_at <= datetime.now(UTC):
        return _oauth_error_redirect(settings, portal="client", code="expired_state")
    portal = transaction.portal
    redirect_uri = transaction.redirect_uri
    code_verifier = transaction.code_verifier
    expected_nonce = transaction.nonce
    return_to = transaction.return_to
    session.delete(transaction)
    session.commit()
    if error or not code:
        return _oauth_error_redirect(settings, portal=portal, code="google_rejected")

    try:
        token_response = httpx.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=15.0,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        raw_id_token = str(token_payload["id_token"])
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            GoogleRequest(),
            settings.google_client_id,
        )
    except Exception:
        return _oauth_error_redirect(
            settings, portal=portal, code="token_exchange_failed"
        )

    if claims.get("nonce") != expected_nonce or not claims.get("email_verified"):
        return _oauth_error_redirect(settings, portal=portal, code="invalid_identity")
    email = str(claims.get("email", "")).strip().casefold()
    subject = str(claims.get("sub", "")).strip()
    if not email or not subject:
        return _oauth_error_redirect(settings, portal=portal, code="missing_identity")
    allowed_domain = settings.google_login_allowed_domain.strip().casefold()
    if allowed_domain and not email.endswith(f"@{allowed_domain}"):
        return _oauth_error_redirect(settings, portal=portal, code="domain_not_allowed")

    user = session.scalar(
        select(AdminUser).where(
            or_(AdminUser.google_subject == subject, AdminUser.email == email)
        )
    )
    # Auto-provisioning is deliberately limited to the client portal.  The
    # administrator portal never creates privileged accounts from Google.
    if user is None and portal == "client" and settings.google_login_auto_provision:
        user = AdminUser(
            username=email,
            email=email,
            display_name=str(claims.get("name") or email.split("@", 1)[0]),
            avatar_url=str(claims.get("picture") or "") or None,
            google_subject=subject,
            auth_provider="google",
            password_hash="!google-only",
            role=AdminRole.CLINIC_ADMIN,
            is_active=True,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        session.flush()
        create_billing_account_for_user(
            session,
            user=user,
            display_name=user.display_name or email,
            billing_email=email,
        )
        session.commit()
        session.refresh(user)
    if user is None:
        return _oauth_error_redirect(
            settings, portal=portal, code="account_not_invited"
        )
    if not user.is_active:
        return _oauth_error_redirect(settings, portal=portal, code="account_disabled")

    user.email = email
    user.google_subject = subject
    user.auth_provider = (
        "google" if user.password_hash == "!google-only" else "password_google"
    )
    user.display_name = str(claims.get("name") or user.display_name or user.username)
    user.avatar_url = str(claims.get("picture") or user.avatar_url or "") or None
    user.last_login_at = datetime.now(UTC)
    user.failed_login_count = 0
    user.locked_until = None
    session.commit()
    session.refresh(user)

    raw_token, csrf_token, _ = create_admin_session(
        session,
        user=user,
        settings=settings,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    destination = _portal_base(settings, portal, user=user) + return_to
    response = RedirectResponse(destination, status_code=status.HTTP_302_FOUND)
    _set_session_cookies(
        response,
        raw_token=raw_token,
        csrf_token=csrf_token,
        settings=settings,
    )
    return response


@router.get("/me", response_model=AdminIdentity)
def me(
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
    session: Annotated[Session, Depends(get_db)],
) -> AdminIdentity:
    """Return the current portal identity and accessible clinics."""
    if principal.user_id is None:
        return AdminIdentity(
            username=principal.username,
            display_name=principal.display_name,
            email=principal.email,
            avatar_url=principal.avatar_url,
            role=principal.role.value,
            clinic_ids=[],
            is_super_admin=True,
        )
    user = session.get(AdminUser, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return _identity_for_user(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Revoke the current browser session and clear shared portal cookies."""
    revoke_admin_session(
        session,
        request.cookies.get(settings.admin_session_cookie_name),
    )
    domain = _cookie_domain(settings)
    response.delete_cookie(settings.admin_session_cookie_name, path="/", domain=domain)
    response.delete_cookie(settings.admin_csrf_cookie_name, path="/", domain=domain)
