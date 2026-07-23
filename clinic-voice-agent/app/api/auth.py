"""Administrator session endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    AdminPrincipal,
    authenticate_admin,
    create_admin_session,
    revoke_admin_session,
)
from app.config import Settings, get_settings
from app.models import AdminMembership
from app.db import get_db
from app.utils.security import require_admin_access

router = APIRouter(prefix="/auth", tags=["admin-auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=1024)


class AdminIdentity(BaseModel):
    username: str
    role: str
    clinic_ids: list[str]
    must_change_password: bool = False


def _secure_cookie(settings: Settings) -> bool:
    return settings.app_environment == "production" or settings.admin_secure_cookies


@router.post("/login", response_model=AdminIdentity)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminIdentity:
    """Authenticate and issue an opaque HttpOnly session cookie."""
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
    max_age = settings.admin_session_ttl_hours * 3600
    response.set_cookie(
        settings.admin_session_cookie_name,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.admin_csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
    )
    clinic_ids = list(
        session.scalars(
            select(AdminMembership.clinic_id).where(AdminMembership.user_id == user.id)
        )
    )
    return AdminIdentity(
        username=user.username,
        role=user.role.value,
        clinic_ids=[str(item) for item in sorted(clinic_ids, key=str)],
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=AdminIdentity)
def me(
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> AdminIdentity:
    """Return the currently authenticated administrator."""
    return AdminIdentity(
        username=principal.username,
        role=principal.role.value,
        clinic_ids=[str(item) for item in sorted(principal.clinic_ids, key=str)],
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Revoke the current browser session and clear cookies."""
    revoke_admin_session(
        session,
        request.cookies.get(settings.admin_session_cookie_name),
    )
    response.delete_cookie(settings.admin_session_cookie_name, path="/")
    response.delete_cookie(settings.admin_csrf_cookie_name, path="/")
