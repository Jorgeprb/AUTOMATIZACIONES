"""Google OAuth endpoints for a clinic account."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import AdminPrincipal
from app.calendar.auth import (
    GoogleOAuthConfigurationError,
    GoogleOAuthCredentialEncryptionError,
    GoogleOAuthError,
    GoogleOAuthPersistenceError,
    GoogleOAuthProviderError,
    InvalidGoogleOAuthState,
    complete_google_oauth,
    create_google_authorization_request,
    decode_google_oauth_state,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Clinic
from app.utils.security import require_admin_access

router = APIRouter(prefix="/auth/google", tags=["google-auth"])
logger = logging.getLogger(__name__)


def _safe_error_type(exc: BaseException) -> str:
    """Return wrapped cause type without leaking exception content."""
    if exc.__cause__ is not None:
        return type(exc.__cause__).__name__
    return type(exc).__name__


def _configuration_error_detail(exc: GoogleOAuthConfigurationError) -> str:
    """Return a concise safe diagnostic message."""
    return "Google OAuth configuration error: " + "; ".join(
        f"{issue.variable}: {issue.message} {issue.help}" for issue in exc.issues
    )


def _frontend_redirect(
    settings: Settings,
    *,
    clinic_id: uuid.UUID | None,
    portal: str = "client",
    outcome: str,
    reason: str,
    message: str,
    account_email: str | None = None,
) -> RedirectResponse:
    """Redirect OAuth browser flow back to the portal that started it."""
    is_admin = portal == "admin"
    base_url = (
        settings.admin_frontend_base_url if is_admin else settings.client_frontend_base_url
    ).rstrip("/")
    if not base_url:
        base_url = "http://localhost:5173" if is_admin else "http://localhost:5174"
    path = (
        f"/clinics/{clinic_id}/calendar"
        if is_admin and clinic_id
        else f"/clinics/{clinic_id}/settings/calendar"
        if clinic_id
        else "/settings"
        if is_admin
        else "/clinics"
    )
    query = {
        "google": outcome,
        "reason": reason,
        "google_oauth": outcome,
        "message": message,
    }
    if account_email:
        query["account_email"] = account_email
    return RedirectResponse(
        f"{base_url}{path}?{urlencode(query)}",
        status_code=status.HTTP_302_FOUND,
    )


def _context_from_state(
    settings: Settings,
    state_value: str | None,
) -> tuple[uuid.UUID | None, str]:
    """Best-effort clinic and portal recovery for callback redirects."""
    if not state_value:
        return None, "client"
    try:
        state = decode_google_oauth_state(settings, state_value)
        return state.clinic_id, state.portal
    except GoogleOAuthError:
        return None, "client"


def _authorization_response_url(settings: Settings, request: Request) -> str:
    """Return the exact public callback URL used for token exchange.

    Local tunnels terminate HTTPS before forwarding to Uvicorn, so
    ``request.url`` may look like ``http://...`` even when Google called the
    public ngrok HTTPS URL. OAuth token exchange must use the configured public
    redirect URI exactly, plus Google's original query string.
    """
    query_string = request.url.query
    if not query_string:
        return settings.google_redirect_uri
    return f"{settings.google_redirect_uri}?{query_string}"


@router.get("/start", response_class=RedirectResponse)
def start_google_oauth(
    clinic_id: Annotated[uuid.UUID, Query()],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> RedirectResponse:
    """Redirect an existing clinic to Google's OAuth consent screen."""
    if not principal.can_write_clinic(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have write access to this clinic.",
        )
    if session.get(Clinic, clinic_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found.",
        )
    try:
        authorization = create_google_authorization_request(
            settings,
            clinic_id,
            portal="admin" if principal.is_super_admin else "client",
        )
    except GoogleOAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_configuration_error_detail(exc),
        ) from exc
    return RedirectResponse(
        authorization.authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback", response_class=RedirectResponse)
def google_oauth_callback(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    state_value: Annotated[str | None, Query(alias="state")] = None,
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Exchange Google's authorization code and store encrypted credentials."""
    clinic_id, portal = _context_from_state(settings, state_value)
    logger.info(
        "google_oauth_callback_received",
        extra={
            "clinic_id": str(clinic_id) if clinic_id else None,
            "redirect_uri": settings.google_redirect_uri,
            "has_code": bool(code),
            "has_error": bool(error),
        },
    )
    if error:
        logger.info(
            "google_oauth_callback_rejected",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "google_error": error,
            },
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="google_rejected",
            message=f"Google authorization failed: {error}",
        )
    if not state_value:
        logger.warning(
            "google_oauth_callback_missing_state",
            extra={"redirect_uri": settings.google_redirect_uri},
        )
        return _frontend_redirect(
            settings,
            clinic_id=None,
            portal=portal,
            outcome="error",
            reason="missing_state",
            message="Google OAuth callback is missing state.",
        )
    try:
        authorization_response = _authorization_response_url(settings, request)
        result = complete_google_oauth(
            session,
            settings,
            state=state_value,
            authorization_response=authorization_response,
        )
    except GoogleOAuthConfigurationError as exc:
        logger.warning(
            "google_oauth_callback_misconfigured",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "variables": [issue.variable for issue in exc.issues],
            },
            exc_info=True,
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="oauth_misconfigured",
            message=_configuration_error_detail(exc),
        )
    except InvalidGoogleOAuthState as exc:
        logger.warning(
            "google_oauth_callback_invalid_state_or_fernet",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="invalid_state",
            message=str(exc),
        )
    except GoogleOAuthProviderError as exc:
        logger.warning(
            "google_oauth_callback_google_failed",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "error_type": _safe_error_type(exc),
            },
            exc_info=True,
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="google_token_exchange_failed",
            message=str(exc),
        )
    except GoogleOAuthCredentialEncryptionError as exc:
        logger.warning(
            "google_oauth_callback_credential_encryption_failed",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "error_type": _safe_error_type(exc),
            },
            exc_info=True,
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="credential_encryption_failed",
            message=str(exc),
        )
    except GoogleOAuthPersistenceError as exc:
        logger.exception(
            "google_oauth_callback_db_failed",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "error_type": _safe_error_type(exc),
            },
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="db_save_failed",
            message=str(exc),
        )
    except GoogleOAuthError as exc:
        logger.warning(
            "google_oauth_callback_failed",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="oauth_failed",
            message=str(exc),
        )
    except Exception as exc:
        session.rollback()
        logger.exception(
            "google_oauth_callback_unexpected_failed",
            extra={
                "clinic_id": str(clinic_id) if clinic_id else None,
                "redirect_uri": settings.google_redirect_uri,
                "error_type": type(exc).__name__,
            },
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            portal=portal,
            outcome="error",
            reason="unexpected_error",
            message="Unexpected Google OAuth callback error. Check backend logs.",
        )
    logger.info(
        "google_oauth_connected",
        extra={
            "clinic_id": str(result.clinic_id),
            "account_email": result.account_email,
            "redirect_uri": settings.google_redirect_uri,
        },
    )
    return _frontend_redirect(
        settings,
        clinic_id=result.clinic_id,
        portal=portal,
        outcome="connected",
        reason="connected",
        message="Google Calendar conectado.",
        account_email=result.account_email,
    )
