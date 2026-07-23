"""Runtime configuration for the standalone SIP gateway."""

from __future__ import annotations

from functools import cached_property
import ipaddress

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Environment-driven settings for SIP/RTP media bridge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_environment: str = "development"
    log_level: str = "INFO"
    sip_bind_host: str = "0.0.0.0"
    sip_port: int = 6060
    sip_public_domain: str = ""
    sip_public_ip: str = ""
    rtp_port_min: int = 10_000
    rtp_port_max: int = 20_000
    rtp_advertise_ip: str = ""
    sip_allowed_ips: str = ""
    rtp_allowed_ips: str = ""
    sip_require_allowlist: bool = True
    sip_datagram_queue_size: int = 1000
    sip_worker_count: int = 4
    sip_transaction_cache_seconds: int = 64
    ack_timeout_seconds: int = 32
    rate_limiter_max_keys: int = 10000
    backend_internal_url: str = "http://app:8000"
    internal_api_key: SecretStr | None = None
    openai_api_key: SecretStr = SecretStr("")
    health_bind_host: str = "0.0.0.0"
    health_port: int = 8088
    max_concurrent_calls: int = 10
    max_call_seconds: int = 1800
    invite_rate_limit_per_minute: int = 60
    fallback_called_number: str | None = None
    silence_energy_threshold: int = 900
    silence_timeout_ms: int = 900
    barge_in_min_frames: int = 8
    barge_in_cooldown_ms: int = 1200
    barge_in_start_guard_ms: int = 600
    external_tts_half_duplex: bool = True
    initial_input_guard_ms: int = 1200
    echo_suppression_tail_ms: int = 800
    tts_text_flush_timeout_ms: int = 650
    tts_min_flush_chars: int = 40
    openai_realtime_ws_url: str = "wss://api.openai.com/v1/realtime"
    openai_project_id: str = ""
    openai_hosted_sip_domain: str = "sip.api.openai.com"
    openai_hosted_sip_transport: str = "tls"
    openai_hosted_sip_strategy: str = "blocked"
    telephony_codec: str = "pcmu"
    rtp_initial_buffer_ms: int = 240
    rtp_packet_log_every: int = 50
    outbound_audio_max_ms: int = 30000
    jitter_buffer_depth: int = 3
    jitter_flush_ms: int = 80
    openai_queue_max_items: int = 500
    openai_input_batch_ms: int = 80

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

    @field_validator(
        "sip_datagram_queue_size",
        "sip_worker_count",
        "sip_transaction_cache_seconds",
        "ack_timeout_seconds",
        "rate_limiter_max_keys",
        "outbound_audio_max_ms",
        "jitter_buffer_depth",
        "jitter_flush_ms",
        "openai_queue_max_items",
        "openai_input_batch_ms",
        "barge_in_min_frames",
        "barge_in_cooldown_ms",
        "barge_in_start_guard_ms",
        "initial_input_guard_ms",
        "echo_suppression_tail_ms",
        "tts_text_flush_timeout_ms",
        "tts_min_flush_chars",
    )
    @classmethod
    def validate_positive_runtime_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("runtime limits must be positive")
        return value

    @field_validator("rtp_packet_log_every")
    @classmethod
    def validate_packet_log_every(cls, value: int) -> int:
        """Keep packet logging rate sane."""
        if not 1 <= value <= 10_000:
            raise ValueError("rtp_packet_log_every must be between 1 and 10000")
        return value

    @model_validator(mode="after")
    def validate_production_network_policy(self) -> "GatewaySettings":
        if (
            self.app_environment.strip().casefold() == "production"
            and self.sip_require_allowlist
            and not self.sip_allowed_ips.strip()
        ):
            raise ValueError("SIP_ALLOWED_IPS is required in production")
        if self.rtp_port_min > self.rtp_port_max:
            raise ValueError("RTP_PORT_MIN must be <= RTP_PORT_MAX")
        return self

    @staticmethod
    def _parse_networks(raw: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for item in raw.split(","):
            value = item.strip()
            if not value:
                continue
            networks.append(ipaddress.ip_network(value, strict=False))
        return tuple(networks)

    @cached_property
    def allowed_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        """Return configured SIP source networks, supporting addresses and CIDRs."""
        return self._parse_networks(self.sip_allowed_ips)

    @cached_property
    def rtp_allowed_networks(self) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        """Return explicit RTP networks; SDP source remains allowed separately."""
        return self._parse_networks(self.rtp_allowed_ips)

    def sip_ip_allowed(self, raw_ip: str) -> bool:
        if not self.allowed_networks:
            return not self.sip_require_allowlist or self.app_environment != "production"
        address = ipaddress.ip_address(raw_ip)
        return any(address in network for network in self.allowed_networks)

    def rtp_ip_explicitly_allowed(self, raw_ip: str) -> bool:
        if not self.rtp_allowed_networks:
            return False
        address = ipaddress.ip_address(raw_ip)
        return any(address in network for network in self.rtp_allowed_networks)

    @property
    def advertised_rtp_ip(self) -> str:
        """Return RTP IP advertised in SDP."""
        return self.rtp_advertise_ip or self.sip_public_ip or self.sip_bind_host

    @property
    def advertised_sip_host(self) -> str:
        """Return SIP host advertised in Contact headers."""
        return self.sip_public_domain or self.sip_public_ip or self.sip_bind_host
