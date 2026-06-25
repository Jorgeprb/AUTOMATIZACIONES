"""Google OAuth endpoints for a clinic account."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.calendar.auth import (
    GoogleOAuthError,
    InvalidGoogleOAuthState,
    complete_google_oauth,
    create_google_authorization_request,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Clinic
from app.schemas import GoogleOAuthCallbackResponse

router = APIRouter(prefix="/auth/google", tags=["google-auth"])


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
    authorization = create_google_authorization_request(settings, clinic_id)
    return RedirectResponse(
        authorization.authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback", response_model=GoogleOAuthCallbackResponse)
def google_oauth_callback(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    state_value: Annotated[str, Query(alias="state")],
    error: Annotated[str | None, Query()] = None,
) -> GoogleOAuthCallbackResponse:
    """Exchange Google's authorization code and store encrypted credentials."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authorization failed: {error}",
        )
    try:
        result = complete_google_oauth(
            session,
            settings,
            state=state_value,
            authorization_response=str(request.url),
        )
    except InvalidGoogleOAuthState as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except GoogleOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return GoogleOAuthCallbackResponse(
        status="connected",
        clinic_id=result.clinic_id,
        account_email=result.account_email,
    )
