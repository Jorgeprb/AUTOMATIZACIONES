"""Security primitives shared by browser and internal integrations."""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.auth import AdminPrincipal, principal_from_session, validate_csrf
from app.config import Settings, get_settings
from app.db import get_db
from app.models import AdminRole

admin_api_key_header = APIKeyHeader(
    name="X-Admin-API-Key",
    scheme_name="AdminApiKey",
    description=(
        "Server-to-server administrative API key. Browser clients use the "
        "HttpOnly administrator session cookie instead."
    ),
    auto_error=False,
)


class TokenCipher:
    """Encrypt and decrypt OAuth tokens using a configured Fernet key."""

    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a token for storage."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str, *, ttl_seconds: int | None = None) -> str:
        """Decrypt a stored token."""
        try:
            return self._fernet.decrypt(
                ciphertext.encode("utf-8"),
                ttl=ttl_seconds,
            ).decode("utf-8")
        except InvalidToken:
            raise


def require_internal_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    supplied_key: Annotated[
        str | None,
        Header(alias="X-Internal-API-Key"),
    ] = None,
) -> None:
    """Protect private gateway, agent-tool, and Calendar endpoints."""
    configured = settings.internal_api_key
    if configured is None:
        if settings.app_environment in {"development", "test"}:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API authentication is not configured.",
        )
    expected = configured.get_secret_value()
    if supplied_key is None or not hmac.compare_digest(supplied_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def _api_key_principal() -> AdminPrincipal:
    return AdminPrincipal(
        user_id=None,
        username="server-api-key",
        display_name="Server API key",
        email=None,
        avatar_url=None,
        role=AdminRole.SUPER_ADMIN,
        clinic_ids=frozenset(),
        clinic_roles={},
        via_api_key=True,
    )


def _enforce_principal_permissions(request: Request, principal: AdminPrincipal) -> None:
    unsafe = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
    raw_clinic_id = request.path_params.get("clinic_id")
    if unsafe and not principal.can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This administrator has read-only access.",
        )
    if raw_clinic_id and not principal.is_super_admin:
        try:
            clinic_id = uuid.UUID(str(raw_clinic_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clinic not found.",
            ) from exc
        if not principal.can_access_clinic(clinic_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this clinic.",
            )
        if unsafe and not principal.can_write_clinic(clinic_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You have read-only access to this clinic.",
            )


def require_admin_access(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    supplied_key: Annotated[str | None, Security(admin_api_key_header)] = None,
) -> AdminPrincipal:
    """Authenticate browser sessions, retaining API-key support for automation."""
    configured = settings.admin_api_key
    if supplied_key and configured is not None and hmac.compare_digest(
        supplied_key,
        configured.get_secret_value(),
    ):
        principal = _api_key_principal()
        request.state.admin_principal = principal
        return principal

    raw_token = request.cookies.get(settings.admin_session_cookie_name)
    resolved = principal_from_session(session, raw_token=raw_token or "") if raw_token else None
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Session"},
        )
    principal, record = resolved
    request_host = request.headers.get("host", "").split(":", 1)[0].casefold()
    if (
        request_host == settings.admin_portal_host.casefold()
        and not principal.is_super_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account must use the client portal.",
        )
    validate_csrf(request, record, settings)
    _enforce_principal_permissions(request, principal)
    request.state.admin_principal = principal
    return principal


def require_admin_api_key(
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> None:
    """Backward-compatible dependency name used by existing routes/tests."""
    _ = principal
