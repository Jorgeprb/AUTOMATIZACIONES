"""Google OAuth web-server flow and encrypted credential persistence."""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow  # type: ignore[import-untyped]
from googleapiclient.discovery import build  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Clinic, GoogleCredential
from app.utils.security import TokenCipher

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
)
OAUTH_STATE_TTL_SECONDS = 10 * 60
FERNET_KEY_HELP = (
    'Generate one with: python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


class GoogleOAuthError(RuntimeError):
    """Base exception for Google OAuth failures."""


class InvalidGoogleOAuthState(GoogleOAuthError):
    """Raised when the OAuth state is invalid, expired, or malformed."""


class GoogleOAuthConfigurationError(GoogleOAuthError):
    """Raised when server-side Google OAuth variables are not usable."""

    def __init__(self, issues: list[GoogleOAuthConfigurationIssue]) -> None:
        self.issues = issues
        variables = ", ".join(issue.variable for issue in issues if issue.is_blocking)
        super().__init__(
            "Google OAuth is not configured correctly."
            + (f" Check: {variables}." if variables else "")
        )


@dataclass(frozen=True, slots=True)
class GoogleOAuthConfigurationIssue:
    """One safe-to-display Google OAuth configuration problem."""

    variable: str
    severity: Literal["error", "warning"]
    message: str
    help: str

    @property
    def is_blocking(self) -> bool:
        """Return whether this issue blocks OAuth start."""
        return self.severity == "error"


@dataclass(frozen=True, slots=True)
class GoogleOAuthConfigurationDiagnostics:
    """Safe diagnostic result for Google OAuth settings."""

    configured: bool
    can_start_oauth: bool
    redirect_uri: str | None
    public_base_url: str | None
    frontend_base_url: str
    issues: list[GoogleOAuthConfigurationIssue]


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


def _looks_placeholder(value: str) -> bool:
    """Detect common example values without exposing the actual secret."""
    lowered = value.strip().casefold()
    return any(
        marker in lowered
        for marker in (
            "replace",
            "changeme",
            "placeholder",
            "your-",
            "tu_",
            "tu-",
        )
    )


def _required_value_issue(
    variable: str,
    help_text: str,
) -> GoogleOAuthConfigurationIssue:
    """Build a consistent missing-value issue."""
    return GoogleOAuthConfigurationIssue(
        variable=variable,
        severity="error",
        message=f"{variable} is missing.",
        help=help_text,
    )


def diagnose_google_oauth_configuration(
    settings: Settings,
) -> GoogleOAuthConfigurationDiagnostics:
    """Return safe diagnostics for the clinic Google OAuth flow."""
    issues: list[GoogleOAuthConfigurationIssue] = []

    client_id = settings.google_client_id.strip()
    client_secret = settings.google_client_secret.get_secret_value().strip()
    redirect_uri = settings.google_redirect_uri.strip()
    encryption_key = settings.google_token_encryption_key.get_secret_value().strip()
    public_base_url = settings.public_base_url.strip()
    frontend_base_url = settings.frontend_base_url.strip() or "http://localhost:5173"

    if not client_id:
        issues.append(
            _required_value_issue(
                "GOOGLE_CLIENT_ID",
                "Create an OAuth Web Client in Google Cloud and paste its client ID.",
            )
        )
    elif _looks_placeholder(client_id):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="GOOGLE_CLIENT_ID",
                severity="error",
                message="GOOGLE_CLIENT_ID still looks like an example value.",
                help="Replace it with the OAuth Client ID from Google Cloud.",
            )
        )

    if not client_secret:
        issues.append(
            _required_value_issue(
                "GOOGLE_CLIENT_SECRET",
                "Paste the OAuth Web Client secret from Google Cloud.",
            )
        )
    elif _looks_placeholder(client_secret):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="GOOGLE_CLIENT_SECRET",
                severity="error",
                message="GOOGLE_CLIENT_SECRET still looks like an example value.",
                help="Replace it with the real client secret. Do not commit it.",
            )
        )

    if not redirect_uri:
        issues.append(
            _required_value_issue(
                "GOOGLE_REDIRECT_URI",
                "Use your public backend callback, for example https://YOUR_DOMAIN/auth/google/callback.",
            )
        )
    elif _looks_placeholder(redirect_uri):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="GOOGLE_REDIRECT_URI",
                severity="error",
                message="GOOGLE_REDIRECT_URI still looks like an example URL.",
                help="Set it to the exact callback URL authorized in Google Cloud.",
            )
        )
    elif not redirect_uri.startswith(("http://", "https://")):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="GOOGLE_REDIRECT_URI",
                severity="error",
                message="GOOGLE_REDIRECT_URI must start with http:// or https://.",
                help=(
                    "For local testing use ngrok/cloudflared or "
                    "http://localhost:8000/auth/google/callback if authorized."
                ),
            )
        )
    elif not redirect_uri.endswith("/auth/google/callback"):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="GOOGLE_REDIRECT_URI",
                severity="warning",
                message="GOOGLE_REDIRECT_URI does not end with /auth/google/callback.",
                help="Make sure Google Cloud contains the exact same redirect URI.",
            )
        )

    if not encryption_key:
        issues.append(
            _required_value_issue(
                "GOOGLE_TOKEN_ENCRYPTION_KEY",
                FERNET_KEY_HELP,
            )
        )
    elif _looks_placeholder(encryption_key):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="GOOGLE_TOKEN_ENCRYPTION_KEY",
                severity="error",
                message=(
                    "GOOGLE_TOKEN_ENCRYPTION_KEY still looks like an example "
                    "value."
                ),
                help=(
                    "Generate a real Fernet key. Keep it stable after "
                    "connecting Google."
                ),
            )
        )
    else:
        try:
            TokenCipher(encryption_key)
        except (TypeError, ValueError) as exc:
            issues.append(
                GoogleOAuthConfigurationIssue(
                    variable="GOOGLE_TOKEN_ENCRYPTION_KEY",
                    severity="error",
                    message="GOOGLE_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.",
                    help=FERNET_KEY_HELP,
                )
            )
            logger.info(
                "google_oauth_invalid_fernet_key",
                extra={"error_type": type(exc).__name__},
            )

    if not public_base_url:
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="PUBLIC_BASE_URL",
                severity="warning",
                message="PUBLIC_BASE_URL is empty.",
                help="Set it to the public backend URL used by OpenAI and webhooks.",
            )
        )
    elif _looks_placeholder(public_base_url):
        issues.append(
            GoogleOAuthConfigurationIssue(
                variable="PUBLIC_BASE_URL",
                severity="warning",
                message="PUBLIC_BASE_URL still looks like an example URL.",
                help=(
                    "Set it to your ngrok/cloudflared URL locally or your "
                    "domain in production."
                ),
            )
        )

    blocking_count = sum(1 for issue in issues if issue.is_blocking)
    return GoogleOAuthConfigurationDiagnostics(
        configured=blocking_count == 0,
        can_start_oauth=blocking_count == 0,
        redirect_uri=redirect_uri or None,
        public_base_url=public_base_url or None,
        frontend_base_url=frontend_base_url,
        issues=issues,
    )


def ensure_google_oauth_configuration(settings: Settings) -> None:
    """Raise a controlled error when Google OAuth cannot be started."""
    diagnostics = diagnose_google_oauth_configuration(settings)
    blocking = [issue for issue in diagnostics.issues if issue.is_blocking]
    if blocking:
        logger.warning(
            "google_oauth_misconfigured",
            extra={"variables": [issue.variable for issue in blocking]},
        )
        raise GoogleOAuthConfigurationError(blocking)


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
    ensure_google_oauth_configuration(settings)
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
