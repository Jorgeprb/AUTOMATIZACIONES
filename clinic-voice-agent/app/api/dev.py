"""Development-only local agent simulation endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_db
from app.simulation import (
    SimulationEngine,
    SimulationTurnRequest,
    SimulationTurnResponse,
)

router = APIRouter(prefix="/dev", tags=["development"])


@router.post(
    "/simulate-agent-turn",
    response_model=SimulationTurnResponse,
)
def simulate_agent_turn(
    payload: SimulationTurnRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SimulationTurnResponse:
    """Run one deterministic conversation turn without OpenAI or SIP."""
    if settings.app_environment == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )
    bind = session.get_bind()
    factory = sessionmaker(
        bind=bind,
        class_=Session,
        expire_on_commit=False,
    )
    engine = SimulationEngine(
        settings=settings,
        session_factory=factory,
        mode=payload.mode,
        now=payload.now,
    )
    try:
        return engine.turn(
            payload.message,
            call_session_id=payload.call_session_id,
            clinic_id=payload.clinic_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
