"""Configuration loading tests."""

from __future__ import annotations

from app.config import Settings, normalize_database_url


def test_settings_load_from_environment() -> None:
    """Required environment values and defaults should load with correct types."""
    settings = Settings(_env_file=None)

    assert settings.openai_project_id == "proj_test"
    assert settings.openai_realtime_model == "gpt-realtime-2"
    assert settings.openai_realtime_voice == "marin"
    assert settings.clinic_timezone == "Europe/Madrid"
    assert settings.openai_sip_uri == "sip:proj_test@sip.api.openai.com;transport=tls"
    assert settings.openai_api_key.get_secret_value() == "test-openai-key"


def test_render_postgres_url_is_normalized_to_psycopg() -> None:
    """Render-style URLs should work without editing DATABASE_URL manually."""
    assert (
        normalize_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )
    assert (
        normalize_database_url("postgres://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_frontend_base_url_is_allowed_in_cors_origins() -> None:
    """Render frontend URL should be accepted even if CORS_ORIGINS is separate."""
    settings = Settings(
        _env_file=None,
        cors_origins="https://other.example.com",
        frontend_base_url="https://frontend.onrender.com",
        database_url="postgresql://user:pass@host:5432/db",
    )

    assert settings.database_url == "postgresql+psycopg://user:pass@host:5432/db"
    assert "https://frontend.onrender.com" in settings.cors_origin_list
