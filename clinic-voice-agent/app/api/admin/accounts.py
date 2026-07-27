"""Super-administrator management of client portal accounts."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import AdminPrincipal, hash_password
from app.db import get_db
from app.models import AdminMembership, AdminRole, AdminSession, AdminUser, Clinic
from app.utils.security import require_admin_access

router = APIRouter(prefix="/admin/users", tags=["Admin · Client accounts"])


class MembershipRead(BaseModel):
    clinic_id: uuid.UUID
    clinic_name: str
    role: AdminRole


class PortalUserRead(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    display_name: str | None
    avatar_url: str | None
    auth_provider: str
    role: AdminRole
    is_active: bool
    google_connected: bool
    memberships: list[MembershipRead]


class PortalUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    role: AdminRole = AdminRole.CLINIC_ADMIN
    clinic_ids: list[uuid.UUID] = Field(default_factory=list)
    temporary_password: str | None = Field(default=None, min_length=10, max_length=1024)
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized:
            raise ValueError("A valid email address is required")
        return normalized


class PortalUserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: AdminRole | None = None
    clinic_ids: list[uuid.UUID] | None = None
    temporary_password: str | None = Field(default=None, min_length=10, max_length=1024)
    is_active: bool | None = None
    unlink_google: bool = False


def _require_super_admin(principal: AdminPrincipal) -> None:
    if not principal.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a global administrator can manage client accounts.",
        )


def _validate_clinics(session: Session, clinic_ids: list[uuid.UUID]) -> None:
    if not clinic_ids:
        return
    found = set(session.scalars(select(Clinic.id).where(Clinic.id.in_(clinic_ids))))
    if found != set(clinic_ids):
        raise HTTPException(status_code=422, detail="One or more clinics do not exist.")


def _serialize(session: Session, user: AdminUser) -> PortalUserRead:
    memberships = list(
        session.execute(
            select(AdminMembership.clinic_id, Clinic.name, AdminMembership.role)
            .join(Clinic, Clinic.id == AdminMembership.clinic_id)
            .where(AdminMembership.user_id == user.id)
            .order_by(Clinic.name)
        )
    )
    return PortalUserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        auth_provider=user.auth_provider,
        role=user.role,
        is_active=user.is_active,
        google_connected=bool(user.google_subject),
        memberships=[
            MembershipRead(clinic_id=clinic_id, clinic_name=name, role=role)
            for clinic_id, name, role in memberships
        ],
    )


def _replace_memberships(
    session: Session,
    *,
    user: AdminUser,
    clinic_ids: list[uuid.UUID],
) -> None:
    _validate_clinics(session, clinic_ids)
    session.execute(delete(AdminMembership).where(AdminMembership.user_id == user.id))
    if user.role != AdminRole.SUPER_ADMIN:
        for clinic_id in sorted(set(clinic_ids), key=str):
            session.add(
                AdminMembership(
                    user_id=user.id,
                    clinic_id=clinic_id,
                    role=user.role,
                )
            )


@router.get("", response_model=list[PortalUserRead])
def list_portal_users(
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> list[PortalUserRead]:
    _require_super_admin(principal)
    users = list(session.scalars(select(AdminUser).order_by(AdminUser.display_name, AdminUser.username)))
    return [_serialize(session, user) for user in users]


@router.post("", response_model=PortalUserRead, status_code=status.HTTP_201_CREATED)
def create_portal_user(
    payload: PortalUserCreate,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> PortalUserRead:
    _require_super_admin(principal)
    if session.scalar(select(AdminUser.id).where(AdminUser.email == payload.email)):
        raise HTTPException(status_code=409, detail="An account already uses this email.")
    if payload.role == AdminRole.SUPER_ADMIN and payload.clinic_ids:
        raise HTTPException(status_code=422, detail="Global administrators do not need clinic memberships.")
    password_hash = (
        hash_password(payload.temporary_password)
        if payload.temporary_password
        else "!google-only"
    )
    user = AdminUser(
        username=payload.email,
        email=payload.email,
        display_name=payload.display_name.strip(),
        password_hash=password_hash,
        auth_provider="password" if payload.temporary_password else "google_invited",
        role=payload.role,
        is_active=payload.is_active,
        must_change_password=bool(payload.temporary_password),
    )
    session.add(user)
    session.flush()
    _replace_memberships(session, user=user, clinic_ids=payload.clinic_ids)
    session.commit()
    session.refresh(user)
    return _serialize(session, user)


@router.patch("/{user_id}", response_model=PortalUserRead)
def update_portal_user(
    user_id: uuid.UUID,
    payload: PortalUserUpdate,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> PortalUserRead:
    _require_super_admin(principal)
    user = session.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    if principal.user_id == user.id and payload.is_active is False:
        raise HTTPException(status_code=422, detail="You cannot disable your own account.")
    if payload.email is not None:
        normalized_email = payload.email.strip().casefold()
        if "@" not in normalized_email:
            raise HTTPException(status_code=422, detail="A valid email address is required.")
        existing = session.scalar(
            select(AdminUser.id).where(
                AdminUser.email == normalized_email,
                AdminUser.id != user.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="An account already uses this email.")
        user.email = normalized_email
        user.username = normalized_email
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.temporary_password is not None:
        user.password_hash = hash_password(payload.temporary_password)
        user.must_change_password = True
        user.auth_provider = "password_google" if user.google_subject else "password"
    if payload.unlink_google:
        user.google_subject = None
        user.avatar_url = None
        user.auth_provider = "password" if user.password_hash != "!google-only" else "google_invited"
    if payload.clinic_ids is not None or payload.role is not None:
        current_ids = list(
            session.scalars(
                select(AdminMembership.clinic_id).where(AdminMembership.user_id == user.id)
            )
        )
        _replace_memberships(
            session,
            user=user,
            clinic_ids=payload.clinic_ids if payload.clinic_ids is not None else current_ids,
        )
    session.commit()
    session.refresh(user)
    return _serialize(session, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portal_user(
    user_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> None:
    _require_super_admin(principal)
    if principal.user_id == user_id:
        raise HTTPException(status_code=422, detail="You cannot delete your own account.")
    user = session.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    session.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
    session.delete(user)
    session.commit()
