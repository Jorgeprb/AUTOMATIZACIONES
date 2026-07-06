"""Runtime configuration for the standalone SIP gateway."""

from __future__ import annotations

from functools import cached_property

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Environment-driven settings for SIP/RTP media bridge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    log_level: str = "INFO"
    sip_bind_host: str = "0.0.0.0"
    sip_port: int = 6060
    sip_public_ip: str = ""
    rtp_port_min: int = 10_000
    rtp_port_max: int = 20_000
    rtp_advertise_ip: str = ""
    sip_allowed_ips: str = ""
    backend_internal_url: str = "http://app:8000"
    internal_api_key: SecretStr | None = None
    openai_api_key: SecretStr = SecretStr("")
    health_bind_host: str = "0.0.0.0"
    health_port: int = 8088
    max_concurrent_calls: int = 10
    max_call_seconds: int = 1800
    invite_rate_limit_per_minute: int = 60
    fallback_called_number: str | None = None
    silence_energy_threshold: int = 350
    silence_timeout_ms: int = 900
    openai_realtime_ws_url: str = "wss://api.openai.com/v1/realtime"

    @field_validator("sip_port", "rtp_port_min", "rtp_port_max", "health_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        """Validate UDP port range."""
        if not 0 <= value <= 65535:
            raise ValueError("port must be between 0 and 65535")
        return value

    @field_validator("max_concurrent_calls")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        """Keep concurrency bounded for small VPS instances."""
        if not 1 <= value <= 500:
            raise ValueError("max_concurrent_calls must be between 1 and 500")
        return value

    @field_validator("rtp_port_max")
    @classmethod
    def validate_rtp_order(cls, value: int) -> int:
        """Field-level sanity; full ordering is checked lazily by pool."""
        return value

    @field_validator("backend_internal_url")
    @classmethod
    def normalize_backend_url(cls, value: str) -> str:
        """Normalize backend URL."""
        return value.rstrip("/")

    @cached_property
    def allowed_ip_set(self) -> set[str]:
        """Return configured SIP source allowlist."""
        return {
            item.strip()
            for item in self.sip_allowed_ips.split(",")
            if item.strip()
        }

    @property
    def advertised_rtp_ip(self) -> str:
        """Return RTP IP advertised in SDP."""
        return self.rtp_advertise_ip or self.sip_public_ip or self.sip_bind_host
