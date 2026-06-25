"""Google OAuth web-server flow and encrypted credential persistence."""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow  # type: ignore[import-untyped]
from googleapiclient.discovery import build  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Clinic, GoogleCredential
from app.utils.security import TokenCipher

GOOGLE_CALENDAR_SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
)
OAUTH_STATE_TTL_SECONDS = 10 * 60


class GoogleOAuthError(RuntimeError):
    """Base exception for Google OAuth failures."""


class InvalidGoogleOAuthState(GoogleOAuthError):
    """Raised when the OAuth state is invalid, expired, or malformed."""


@dataclass(frozen=True, slots=True)
class GoogleAuthorizationRequest:
    """Authorization URL and encrypted state returned by an OAuth flow."""

    authorization_url: str
    state: str


@dataclass(frozen=True, slots=True)
class GoogleOAuthState:
    """Trusted application context recovered from OAuth state."""

    clinic_id: uuid.UUID
    code_verifier: str


@dataclass(frozen=True, slots=True)
class GoogleOAuthResult:
    """Account connected after a successful OAuth callback."""

    clinic_id: uuid.UUID
    account_email: str


def _client_config(settings: Settings) -> dict[str, Any]:
    """Build the client configuration expected by google-auth-oauthlib."""
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret.get_secret_value(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _build_flow(
    settings: Settings,
    *,
    state: str | None = None,
    code_verifier: str | None = None,
) -> Flow:
    """Create an OAuth flow for the configured web client."""
    flow = Flow.from_client_config(
        _client_config(settings),
        scopes=GOOGLE_CALENDAR_SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is None,
    )
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def create_google_authorization_request(
    settings: Settings,
    clinic_id: uuid.UUID,
) -> GoogleAuthorizationRequest:
    """Create an offline OAuth authorization URL for one clinic."""
    code_verifier = secrets.token_urlsafe(64)
    state_payload = json.dumps(
        {
            "clinic_id": str(clinic_id),
            "nonce": secrets.token_urlsafe(24),
            "code_verifier": code_verifier,
        },
        separators=(",", ":"),
    )
    state = TokenCipher(
        settings.google_token_encryption_key.get_secret_value()
    ).encrypt(state_payload)
    flow = _build_flow(
        settings,
        state=state,
        code_verifier=code_verifier,
    )
    authorization_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return GoogleAuthorizationRequest(
        authorization_url=authorization_url,
        state=returned_state,
    )


def decode_google_oauth_state(
    settings: Settings,
    state: str,
) -> GoogleOAuthState:
    """Validate and decode the short-lived OAuth state."""
    try:
        plaintext = TokenCipher(
            settings.google_token_encryption_key.get_secret_value()
        ).decrypt(state, ttl_seconds=OAUTH_STATE_TTL_SECONDS)
        payload = json.loads(plaintext)
        clinic_id = uuid.UUID(payload["clinic_id"])
        if not payload.get("nonce"):
            raise ValueError("missing nonce")
        code_verifier = str(payload["code_verifier"])
        if not 43 <= len(code_verifier) <= 128:
            raise ValueError("invalid PKCE code verifier")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidGoogleOAuthState("Google OAuth state is invalid.") from exc
    except Exception as exc:
        raise InvalidGoogleOAuthState(
            "Google OAuth state is invalid or expired."
        ) from exc
    return GoogleOAuthState(
        clinic_id=clinic_id,
        code_verifier=code_verifier,
    )


def _merge_existing_refresh_token(
    session: Session,
    settings: Settings,
    clinic_id: uuid.UUID,
    credentials_json: str,
) -> str:
    """Preserve the previous refresh token when Google omits it."""
    new_payload = json.loads(credentials_json)
    if new_payload.get("refresh_token"):
        return credentials_json

    existing = session.scalar(
        select(GoogleCredential).where(GoogleCredential.clinic_id == clinic_id)
    )
    if existing is None:
        return credentials_json

    old_json = TokenCipher(
        settings.google_token_encryption_key.get_secret_value()
    ).decrypt(existing.token_json_encrypted)
    old_payload = json.loads(old_json)
    if old_payload.get("refresh_token"):
        new_payload["refresh_token"] = old_payload["refresh_token"]
    return json.dumps(new_payload)


def save_google_credentials(
    session: Session,
    settings: Settings,
    *,
    clinic_id: uuid.UUID,
    account_email: str,
    credentials_json: str,
) -> GoogleCredential:
    """Encrypt and upsert credentials for the clinic's single Google account."""
    credentials_json = _merge_existing_refresh_token(
        session,
        settings,
        clinic_id,
        credentials_json,
    )
    encrypted = TokenCipher(
        settings.google_token_encryption_key.get_secret_value()
    ).encrypt(credentials_json)
    stored = session.scalar(
        select(GoogleCredential).where(GoogleCredential.clinic_id == clinic_id)
    )
    if stored is None:
        stored = GoogleCredential(
            clinic_id=clinic_id,
            account_email=account_email,
            token_json_encrypted=encrypted,
        )
        session.add(stored)
    else:
        stored.account_email = account_email
        stored.token_json_encrypted = encrypted
    session.commit()
    return stored


def complete_google_oauth(
    session: Session,
    settings: Settings,
    *,
    state: str,
    authorization_response: str,
) -> GoogleOAuthResult:
    """Exchange the callback code and persist encrypted Google credentials."""
    oauth_state = decode_google_oauth_state(settings, state)
    clinic = session.get(Clinic, oauth_state.clinic_id)
    if clinic is None:
        raise GoogleOAuthError("Clinic does not exist.")

    flow = _build_flow(
        settings,
        state=state,
        code_verifier=oauth_state.code_verifier,
    )
    flow.fetch_token(authorization_response=authorization_response)
    credentials: Credentials = flow.credentials
    oauth_service = build(
        "oauth2",
        "v2",
        credentials=credentials,
        cache_discovery=False,
    )
    user_info = oauth_service.userinfo().get().execute()
    account_email = str(user_info["email"])
    save_google_credentials(
        session,
        settings,
        clinic_id=clinic.id,
        account_email=account_email,
        credentials_json=credentials.to_json(),
    )
    return GoogleOAuthResult(
        clinic_id=clinic.id,
        account_email=account_email,
    )
