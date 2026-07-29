"""Configuration loading tests."""

from __future__ import annotations

from app.config import Settings, normalize_database_url


def _database_url(scheme: str, target: str) -> str:
    credentials = ":".join(("test_user", "test_password"))
    return f"{scheme}://{credentials}@{target}"


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
    assert normalize_database_url(
        _database_url("postgresql", "host:5432/db")
    ) == _database_url("postgresql+psycopg", "host:5432/db")
    assert normalize_database_url(
        _database_url("postgres", "host:5432/db")
    ) == _database_url("postgresql+psycopg", "host:5432/db")


def test_supabase_postgres_url_requires_ssl() -> None:
    """Supabase URLs should use psycopg and SSL by default."""
    assert (
        normalize_database_url(
            _database_url("postgresql", "db.project.supabase.co:5432/postgres")
        )
        == _database_url("postgresql+psycopg", "db.project.supabase.co:5432/postgres")
        + "?sslmode=require"
    )
    assert (
        normalize_database_url(
            _database_url("postgresql", "aws-0-eu.pooler.supabase.com:6543/postgres")
            + "?sslmode=verify-full"
        )
        == _database_url(
            "postgresql+psycopg", "aws-0-eu.pooler.supabase.com:6543/postgres"
        )
        + "?sslmode=verify-full"
    )


def test_frontend_base_url_is_allowed_in_cors_origins() -> None:
    """Render frontend URL should be accepted even if CORS_ORIGINS is separate."""
    settings = Settings(
        _env_file=None,
        cors_origins="https://other.example.com",
        frontend_base_url="https://frontend.onrender.com",
        database_url=_database_url("postgresql", "host:5432/db"),
    )

    assert settings.database_url == _database_url("postgresql+psycopg", "host:5432/db")
    assert "https://frontend.onrender.com" in settings.cors_origin_list
