"""Shared deterministic environment for tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app import models as domain_models  # noqa: F401
from app.db import Base

TEST_ENVIRONMENT = {
    "APP_ENVIRONMENT": "test",
    "INTERNAL_API_KEY": "test-internal-api-key-with-32-characters",
    "ADMIN_API_KEY": "test-admin-api-key-with-32-characters",
    "ENABLE_CALL_TRANSCRIPTION": "true",
    "PUBLIC_RATE_LIMIT_PER_MINUTE": "60",
    "WEBHOOK_RATE_LIMIT_PER_MINUTE": "120",
    "MAX_WEBHOOK_BODY_BYTES": "1000000",
    "CORS_ORIGINS": "http://localhost:5173",
    "OPENAI_API_KEY": "test-openai-key",
    "OPENAI_WEBHOOK_SECRET": "test-webhook-secret",
    "OPENAI_PROJECT_ID": "proj_test",
    "OPENAI_REALTIME_MODEL": "gpt-realtime-2",
    "OPENAI_REALTIME_VOICE": "marin",
    "PUBLIC_BASE_URL": "https://example.test",
    "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5432/test",
    "GOOGLE_CLIENT_ID": "test-google-client-id",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "GOOGLE_REDIRECT_URI": "https://example.test/auth/google/callback",
    "GOOGLE_TOKEN_ENCRYPTION_KEY": "8O2kjVBitzftnS456ehnuY5iSmFpJbqJNUnWVallRe4=",
    "CLINIC_TIMEZONE": "Europe/Madrid",
    "CLINIC_NAME": "Clínica Test",
    "CLINIC_PHONE_NUMBER": "+34910000000",
}

for name, value in TEST_ENVIRONMENT.items():
    if name == "DATABASE_URL":
        os.environ.setdefault(name, value)
    else:
        os.environ[name] = value


@pytest.fixture
def anyio_backend() -> str:
    """Run async HTTP tests on the standard asyncio backend only."""
    return "asyncio"


@pytest.fixture
def database_engine() -> Generator[Engine, None, None]:
    """Create an isolated PostgreSQL schema for one test."""
    database_url = os.environ["DATABASE_URL"]
    schema_name = f"test_{uuid.uuid4().hex}"
    admin_engine = create_engine(database_url, pool_pre_ping=True)

    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema_name))

    test_engine = create_engine(
        database_url,
        connect_args={"options": f"-csearch_path={schema_name}"},
        pool_pre_ping=True,
    )
    Base.metadata.create_all(test_engine)

    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema_name, cascade=True))
        admin_engine.dispose()


@pytest.fixture
def db_session(database_engine: Engine) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session bound to an isolated test schema."""
    session_factory = sessionmaker(
        bind=database_engine,
        class_=Session,
        expire_on_commit=False,
    )
    with session_factory() as session:
        yield session
