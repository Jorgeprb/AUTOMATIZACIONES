"""Google OAuth endpoints for a clinic account."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.calendar.auth import (
    GoogleOAuthConfigurationError,
    GoogleOAuthError,
    InvalidGoogleOAuthState,
    complete_google_oauth,
    create_google_authorization_request,
    decode_google_oauth_state,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Clinic

router = APIRouter(prefix="/auth/google", tags=["google-auth"])
logger = logging.getLogger(__name__)


def _configuration_error_detail(exc: GoogleOAuthConfigurationError) -> str:
    """Return a concise safe diagnostic message."""
    return "Google OAuth configuration error: " + "; ".join(
        f"{issue.variable}: {issue.message} {issue.help}" for issue in exc.issues
    )


def _frontend_redirect(
    settings: Settings,
    *,
    clinic_id: uuid.UUID | None,
    outcome: str,
    message: str,
    account_email: str | None = None,
) -> RedirectResponse:
    """Redirect OAuth browser flow back to the administration panel."""
    base_url = settings.frontend_base_url.rstrip("/") or "http://localhost:5173"
    path = f"/clinics/{clinic_id}/calendar" if clinic_id else "/settings"
    query = {
        "google_oauth": outcome,
        "message": message,
    }
    if account_email:
        query["account_email"] = account_email
    return RedirectResponse(
        f"{base_url}{path}?{urlencode(query)}",
        status_code=status.HTTP_302_FOUND,
    )


def _clinic_id_from_state(
    settings: Settings,
    state_value: str | None,
) -> uuid.UUID | None:
    """Best-effort clinic recovery for callback error redirects."""
    if not state_value:
        return None
    try:
        return decode_google_oauth_state(settings, state_value).clinic_id
    except GoogleOAuthError:
        return None


@router.get("/start", response_class=RedirectResponse)
def start_google_oauth(
    clinic_id: Annotated[uuid.UUID, Query()],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Redirect an existing clinic to Google's OAuth consent screen."""
    if session.get(Clinic, clinic_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found.",
        )
    try:
        authorization = create_google_authorization_request(settings, clinic_id)
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
    state_value: Annotated[str, Query(alias="state")],
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Exchange Google's authorization code and store encrypted credentials."""
    clinic_id = _clinic_id_from_state(settings, state_value)
    if error:
        logger.info(
            "google_oauth_callback_rejected",
            extra={"clinic_id": clinic_id, "google_error": error},
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            outcome="error",
            message=f"Google authorization failed: {error}",
        )
    try:
        result = complete_google_oauth(
            session,
            settings,
            state=state_value,
            authorization_response=str(request.url),
        )
    except GoogleOAuthConfigurationError as exc:
        logger.warning(
            "google_oauth_callback_misconfigured",
            extra={"variables": [issue.variable for issue in exc.issues]},
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            outcome="error",
            message=_configuration_error_detail(exc),
        )
    except InvalidGoogleOAuthState as exc:
        logger.info("google_oauth_callback_invalid_state")
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            outcome="error",
            message=str(exc),
        )
    except GoogleOAuthError as exc:
        logger.warning(
            "google_oauth_callback_failed",
            extra={"clinic_id": clinic_id, "error_type": type(exc).__name__},
        )
        return _frontend_redirect(
            settings,
            clinic_id=clinic_id,
            outcome="error",
            message=str(exc),
        )
    logger.info(
        "google_oauth_connected",
        extra={"clinic_id": result.clinic_id, "account_email": result.account_email},
    )
    return _frontend_redirect(
        settings,
        clinic_id=result.clinic_id,
        outcome="connected",
        message="Google Calendar conectado.",
        account_email=result.account_email,
    )
