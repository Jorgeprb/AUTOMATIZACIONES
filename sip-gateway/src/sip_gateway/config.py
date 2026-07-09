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
    sip_public_domain: str = ""
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
    openai_project_id: str = ""
    openai_hosted_sip_domain: str = "sip.api.openai.com"
    openai_hosted_sip_transport: str = "tls"
    openai_hosted_sip_strategy: str = "blocked"
    telephony_codec: str = "pcmu"
    rtp_initial_buffer_ms: int = 240
    rtp_packet_log_every: int = 50

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

    @field_validator("backend_internal_url")
    @classmethod
    def normalize_backend_url(cls, value: str) -> str:
        """Normalize backend URL."""
        return value.rstrip("/")

    @field_validator("telephony_codec")
    @classmethod
    def normalize_telephony_codec(cls, value: str) -> str:
        """Normalize selected G.711 codec."""
        normalized = value.strip().casefold()
        if normalized not in {"pcma", "pcmu"}:
            raise ValueError("TELEPHONY_CODEC must be pcma or pcmu")
        return normalized

    @field_validator("openai_hosted_sip_strategy")
    @classmethod
    def normalize_hosted_sip_strategy(cls, value: str) -> str:
        """Normalize hosted SIP behavior for providers that cannot follow 302."""
        normalized = value.strip().casefold()
        if normalized not in {"blocked", "redirect"}:
            raise ValueError("OPENAI_HOSTED_SIP_STRATEGY must be blocked or redirect")
        return normalized

    @field_validator("rtp_initial_buffer_ms")
    @classmethod
    def validate_initial_buffer(cls, value: int) -> int:
        """Keep initial RTP playout buffer in a telephone-safe range."""
        if not 20 <= value <= 1000:
            raise ValueError("rtp_initial_buffer_ms must be between 20 and 1000")
        return value

    @field_validator("rtp_packet_log_every")
    @classmethod
    def validate_packet_log_every(cls, value: int) -> int:
        """Keep packet logging rate sane."""
        if not 1 <= value <= 10_000:
            raise ValueError("rtp_packet_log_every must be between 1 and 10000")
        return value

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

    @property
    def advertised_sip_host(self) -> str:
        """Return SIP host advertised in Contact headers."""
        return self.sip_public_domain or self.sip_public_ip or self.sip_bind_host
