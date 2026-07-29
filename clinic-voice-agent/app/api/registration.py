"""Public self-registration, email verification and password recovery."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import AdminIdentity, _identity_for_user, _set_session_cookies
from app.auth import AdminPrincipal, create_admin_session, hash_password
from app.config import Settings, get_settings
from app.db import get_db
from app.enterprise_schemas import (
    EmailRequest,
    OnboardingClinicRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenRequest,
)
from app.enterprise_service import (
    account_for_user,
    consume_action_token,
    create_action_token,
    create_billing_account_for_user,
    create_clinic_for_account,
    enqueue_outbox,
    normalize_email,
    require_principal_user,
)
from app.models import AdminRole, AdminSession, AdminUser
from app.utils.security import require_admin_access

router = APIRouter(prefix="/auth", tags=["portal-registration"])


def _email_link(settings: Settings, path: str, token: str) -> str:
    base = settings.client_frontend_base_url.rstrip("/")
    return f"{base}{path}?token={token}"


@router.post(
    "/register", response_model=AdminIdentity, status_code=status.HTTP_201_CREATED
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminIdentity:
    if not settings.registration_enabled:
        raise HTTPException(status_code=404, detail="Registration is disabled.")
    email = normalize_email(payload.email)
    existing = session.scalar(
        select(AdminUser).where(
            or_(AdminUser.email == email, AdminUser.username == email)
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="Ya existe una cuenta con ese correo."
        )
    user = AdminUser(
        username=email,
        email=email,
        display_name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        auth_provider="password",
        role=AdminRole.CLINIC_ADMIN,
        is_active=True,
        must_change_password=False,
    )
    session.add(user)
    session.flush()
    create_billing_account_for_user(
        session,
        user=user,
        display_name=payload.name,
        billing_email=email,
    )
    raw_verification = create_action_token(
        session,
        user_id=user.id,
        kind="verify_email",
        ttl=timedelta(hours=settings.email_verification_ttl_hours),
    )
    enqueue_outbox(
        session,
        kind="email.send",
        dedupe_key=f"verify-email:{user.id}:{hashlib.sha256(raw_verification.encode()).hexdigest()}",
        payload={
            "to": email,
            "subject": "Verifica tu correo de Autogal",
            "text": f"Verifica tu correo aquí: {_email_link(settings, '/verify-email', raw_verification)}",
        },
    )
    session.commit()
    session.refresh(user)
    raw_token, csrf_token, _ = create_admin_session(
        session,
        user=user,
        settings=settings,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    _set_session_cookies(
        response, raw_token=raw_token, csrf_token=csrf_token, settings=settings
    )
    return _identity_for_user(session, user)


@router.post("/verify-email", status_code=204)
def verify_email(
    payload: TokenRequest, session: Annotated[Session, Depends(get_db)]
) -> None:
    token = consume_action_token(session, raw_token=payload.token, kind="verify_email")
    if token is None:
        raise HTTPException(
            status_code=400, detail="El enlace no es válido o ha caducado."
        )
    user = session.get(AdminUser, token.user_id)
    if user is None:
        raise HTTPException(
            status_code=400, detail="El enlace no es válido o ha caducado."
        )
    from datetime import UTC, datetime

    user.email_verified_at = datetime.now(UTC)
    session.commit()


@router.post("/resend-verification", status_code=202)
def resend_verification(
    payload: EmailRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    email = payload.email.strip().casefold()
    user = session.scalar(select(AdminUser).where(AdminUser.email == email))
    if user is not None and user.email_verified_at is None:
        raw = create_action_token(
            session,
            user_id=user.id,
            kind="verify_email",
            ttl=timedelta(hours=settings.email_verification_ttl_hours),
        )
        enqueue_outbox(
            session,
            kind="email.send",
            dedupe_key=f"verify-email:{user.id}:{hashlib.sha256(raw.encode()).hexdigest()}",
            payload={
                "to": email,
                "subject": "Verifica tu correo de Autogal",
                "text": f"Verifica tu correo aquí: {_email_link(settings, '/verify-email', raw)}",
            },
        )
        session.commit()
    return {"message": "Si la cuenta existe, recibirás un correo."}


@router.post("/forgot-password", status_code=202)
def forgot_password(
    payload: EmailRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    email = payload.email.strip().casefold()
    user = session.scalar(select(AdminUser).where(AdminUser.email == email))
    if user is not None and user.is_active:
        raw = create_action_token(
            session,
            user_id=user.id,
            kind="reset_password",
            ttl=timedelta(minutes=settings.password_reset_ttl_minutes),
        )
        enqueue_outbox(
            session,
            kind="email.send",
            dedupe_key=f"password-reset:{user.id}:{hashlib.sha256(raw.encode()).hexdigest()}",
            payload={
                "to": email,
                "subject": "Restablece tu contraseña de Autogal",
                "text": f"Restablece tu contraseña aquí: {_email_link(settings, '/reset-password', raw)}",
            },
        )
        session.commit()
    return {"message": "Si la cuenta existe, recibirás un correo."}


@router.post("/reset-password", status_code=204)
def reset_password(
    payload: PasswordResetRequest, session: Annotated[Session, Depends(get_db)]
) -> None:
    token = consume_action_token(
        session, raw_token=payload.token, kind="reset_password"
    )
    if token is None:
        raise HTTPException(
            status_code=400, detail="El enlace no es válido o ha caducado."
        )
    user = session.get(AdminUser, token.user_id)
    if user is None:
        raise HTTPException(
            status_code=400, detail="El enlace no es válido o ha caducado."
        )
    user.password_hash = hash_password(payload.password)
    user.must_change_password = False
    session.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
    session.commit()


@router.post("/onboarding/clinic", response_model=dict, status_code=201)
def onboarding_clinic(
    payload: OnboardingClinicRequest,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> dict[str, str]:
    user_id = require_principal_user(principal)
    user = session.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    account = account_for_user(session, user.id)
    if account is None:
        account = create_billing_account_for_user(
            session,
            user=user,
            display_name=user.display_name or user.username,
            billing_email=user.email or user.username,
        )
    clinic = create_clinic_for_account(
        session,
        account=account,
        owner=user,
        name=payload.name,
        timezone=payload.timezone,
        main_phone_number=payload.main_phone_number,
        email=payload.email,
        address=payload.address,
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una clínica con ese teléfono principal.",
        ) from exc
    return {"clinic_id": str(clinic.id), "billing_account_id": str(account.id)}


@router.post("/onboarding/clinics", response_model=dict, status_code=201)
def create_additional_clinic(
    payload: OnboardingClinicRequest,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> dict[str, str]:
    return onboarding_clinic(payload, session, principal)
