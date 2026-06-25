"""Service health endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Report that the application process is running."""
    return HealthResponse(
        status="ok",
        service="clinic-voice-agent",
        environment=settings.app_environment,
    )


@router.get("/health/live", response_model=HealthResponse)
def liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Report that the Python process can serve requests."""
    return HealthResponse(
        status="ok",
        service="clinic-voice-agent",
        environment=settings.app_environment,
    )


@router.get("/health/ready", response_model=HealthResponse)
def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
) -> HealthResponse:
    """Report readiness only when PostgreSQL answers."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready.",
        ) from exc
    return HealthResponse(
        status="ok",
        service="clinic-voice-agent",
        environment=settings.app_environment,
    )
