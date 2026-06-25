"""Configuration loading tests."""

from __future__ import annotations

from app.config import Settings


def test_settings_load_from_environment() -> None:
    """Required environment values and defaults should load with correct types."""
    settings = Settings(_env_file=None)

    assert settings.openai_project_id == "proj_test"
    assert settings.openai_realtime_model == "gpt-realtime-2"
    assert settings.openai_realtime_voice == "marin"
    assert settings.clinic_timezone == "Europe/Madrid"
    assert settings.openai_sip_uri == "sip:proj_test@sip.api.openai.com;transport=tls"
    assert settings.openai_api_key.get_secret_value() == "test-openai-key"
