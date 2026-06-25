"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(value: str) -> str:
    """Normalize hosted Postgres URLs to the installed psycopg driver.

    Render and Supabase commonly expose plain ``postgresql://`` or
    ``postgres://`` URLs. The app uses the SQLAlchemy psycopg driver, so those
    URLs are converted to ``postgresql+psycopg://``. Supabase hosts also get
    ``sslmode=require`` when the parameter is missing.
    """
    if value.startswith("postgresql+psycopg://"):
        normalized = value
    elif value.startswith("postgresql://"):
        normalized = value.replace("postgresql://", "postgresql+psycopg://", 1)
    elif value.startswith("postgres://"):
        normalized = value.replace("postgres://", "postgresql+psycopg://", 1)
    else:
        return value

    parsed = urlsplit(normalized)
    hostname = parsed.hostname or ""
    if "supabase." not in hostname and "supabase.com" not in hostname:
        return normalized

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key.lower() == "sslmode" for key, _ in query_pairs):
        return normalized

    query = urlencode([*query_pairs, ("sslmode", "require")])
    return urlunsplit(parsed._replace(query=query))


class Settings(BaseSettings):
    """Typed runtime settings.

    Values are read from the process environment and, for local development,
    from a `.env` file in the current working directory.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    internal_api_key: SecretStr | None = None
    admin_api_key: SecretStr | None = None
    enable_call_transcription: bool = False
    public_rate_limit_per_minute: int = 60
    webhook_rate_limit_per_minute: int = 120
    max_webhook_body_bytes: int = 1_000_000
    cors_origins: str = "http://localhost:5173"

    openai_api_key: SecretStr
    openai_webhook_secret: SecretStr
    openai_project_id: str
    openai_realtime_model: str = "gpt-realtime-2"
    openai_realtime_voice: str = "marin"
    openai_realtime_models: str = "gpt-realtime-2"
    openai_realtime_voices: str = (
        "marin,cedar,alloy,ash,ballad,coral,echo,sage,shimmer,verse"
    )
    test_console_engine: Literal["simulator", "openai"] = "simulator"
    test_console_model: str = "gpt-5.4-mini"

    public_base_url: str
    frontend_base_url: str = "http://localhost:5173"
    database_url: str

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = ""
    google_token_encryption_key: SecretStr = SecretStr("")

    clinic_timezone: str = "Europe/Madrid"
    clinic_name: str
    clinic_phone_number: str

    @model_validator(mode="after")
    def validate_environment_requirements(self) -> Settings:
        """Require production-only secrets and public HTTPS URLs."""
        if self.app_environment != "production":
            return self
        if self.internal_api_key is None:
            raise ValueError("INTERNAL_API_KEY is required in production")
        if self.admin_api_key is None:
            raise ValueError("ADMIN_API_KEY is required in production")
        internal_key = self.internal_api_key.get_secret_value()
        admin_key = self.admin_api_key.get_secret_value()
        if len(internal_key) < 32:
            raise ValueError("INTERNAL_API_KEY must contain at least 32 characters")
        if len(admin_key) < 32:
            raise ValueError("ADMIN_API_KEY must contain at least 32 characters")
        if not self.public_base_url.startswith("https://"):
            raise ValueError("PUBLIC_BASE_URL must use https in production")
        if not self.google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID is required in production")
        if not self.google_redirect_uri:
            raise ValueError("GOOGLE_REDIRECT_URI is required in production")
        if not self.google_redirect_uri.startswith("https://"):
            raise ValueError("GOOGLE_REDIRECT_URI must use https in production")
        placeholders = ("replace", "changeme", "example")
        secrets = {
            "OPENAI_API_KEY": self.openai_api_key.get_secret_value(),
            "OPENAI_WEBHOOK_SECRET": (self.openai_webhook_secret.get_secret_value()),
            "GOOGLE_CLIENT_SECRET": self.google_client_secret.get_secret_value(),
            "GOOGLE_TOKEN_ENCRYPTION_KEY": (
                self.google_token_encryption_key.get_secret_value()
            ),
        }
        for name, value in secrets.items():
            if not value or any(marker in value.casefold() for marker in placeholders):
                raise ValueError(f"{name} must contain a real production value")
        return self

    @field_validator("public_base_url", "google_redirect_uri", "frontend_base_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        """Require externally usable HTTP(S) URLs and normalize trailing slashes."""
        if not value:
            return value
        if not value.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Accept Render-style PostgreSQL URLs and force psycopg driver usage."""
        normalized = normalize_database_url(value)
        if not normalized.startswith(("postgresql+psycopg://", "sqlite://")):
            raise ValueError(
                "DATABASE_URL must start with postgresql://, postgres://, "
                "postgresql+psycopg:// or sqlite://"
            )
        return normalized

    @field_validator("clinic_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Ensure the configured IANA timezone exists."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize and validate the standard logging level."""
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be a valid Python logging level")
        return normalized

    @field_validator(
        "public_rate_limit_per_minute",
        "webhook_rate_limit_per_minute",
    )
    @classmethod
    def validate_rate_limit(cls, value: int) -> int:
        """Require useful positive rate limits."""
        if not 1 <= value <= 10_000:
            raise ValueError("must be between 1 and 10000")
        return value

    @field_validator("max_webhook_body_bytes")
    @classmethod
    def validate_webhook_size(cls, value: int) -> int:
        """Keep webhook bodies bounded before parsing."""
        if not 1_024 <= value <= 10_000_000:
            raise ValueError("must be between 1024 and 10000000")
        return value

    @property
    def openai_sip_uri(self) -> str:
        """Return the OpenAI SIP target associated with this project."""
        return f"sip:{self.openai_project_id}@sip.api.openai.com;transport=tls"

    @property
    def openai_webhook_url(self) -> str:
        """Return the public URL intended for OpenAI Realtime webhooks."""
        return f"{self.public_base_url}/webhooks/openai/realtime"

    @property
    def openai_realtime_model_list(self) -> list[str]:
        """Return configured Realtime models with the default first."""
        values = [
            value.strip()
            for value in self.openai_realtime_models.split(",")
            if value.strip()
        ]
        return list(dict.fromkeys([self.openai_realtime_model, *values]))

    @property
    def openai_realtime_voice_list(self) -> list[str]:
        """Return configured Realtime voices with the default first."""
        values = [
            value.strip()
            for value in self.openai_realtime_voices.split(",")
            if value.strip()
        ]
        return list(dict.fromkeys([self.openai_realtime_voice, *values]))

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized comma-separated browser origins."""
        origins = [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]
        if self.frontend_base_url and self.frontend_base_url not in origins:
            origins.append(self.frontend_base_url)
        return origins


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object per process."""
    return Settings()
