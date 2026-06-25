"""Security primitives shared by external integrations."""

from __future__ import annotations

import hmac
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

admin_api_key_header = APIKeyHeader(
    name="X-Admin-API-Key",
    scheme_name="AdminApiKey",
    description="API key used by the multi-clinic administration backend.",
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
        """Decrypt a stored token.

        `InvalidToken` is intentionally allowed to propagate so callers cannot
        mistake corrupt or incorrectly keyed data for a valid credential.
        """
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
    """Protect administrative and agent-tool endpoints."""
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


def require_admin_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    supplied_key: Annotated[
        str | None,
        Security(admin_api_key_header),
    ] = None,
) -> None:
    """Protect every multi-clinic administration endpoint."""
    configured = settings.admin_api_key
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API authentication is not configured.",
        )
    expected = configured.get_secret_value()
    if supplied_key is None or not hmac.compare_digest(supplied_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
