"""Health endpoint tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import get_db
from app.main import create_app


@pytest.mark.anyio
async def test_health_endpoint() -> None:
    """The process health endpoint should be lightweight and successful."""
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "clinic-voice-agent",
        "environment": "test",
    }
    assert response.headers["X-Request-ID"]


@pytest.mark.anyio
async def test_live_and_ready_health_endpoints(
    database_engine: Engine,
) -> None:
    """Liveness should be cheap and readiness should check PostgreSQL."""
    factory = sessionmaker(
        bind=database_engine,
        class_=Session,
        expire_on_commit=False,
    )
    app = create_app()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.json()["status"] == "ok"
