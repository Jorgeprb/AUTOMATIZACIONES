"""Shared helpers for administrative CRUD endpoints."""

from __future__ import annotations

import math
import uuid
from typing import Any, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin_schemas import Page
from app.models import Clinic

ModelT = TypeVar("ModelT")
SchemaT = TypeVar("SchemaT")


def clinic_or_404(session: Session, clinic_id: uuid.UUID) -> Clinic:
    """Return one clinic or a stable 404 response."""
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found.",
        )
    return clinic


def nested_or_404(
    session: Session,
    model: type[ModelT],
    *,
    clinic_id: uuid.UUID,
    resource_id: uuid.UUID,
    label: str,
) -> ModelT:
    """Return a tenant-owned resource without allowing cross-clinic access."""
    resource = session.scalar(
        select(model).where(
            model.id == resource_id,  # type: ignore[attr-defined]
            model.clinic_id == clinic_id,  # type: ignore[attr-defined]
        )
    )
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} not found.",
        )
    return resource


def commit_or_conflict(
    session: Session,
    *,
    detail: str = "A resource with these values already exists.",
) -> None:
    """Commit a mutation and turn integrity errors into HTTP 409."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


def apply_update(instance: object, payload: object) -> None:
    """Apply fields explicitly supplied in a Pydantic update model."""
    values = payload.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
    for field, value in values.items():
        setattr(instance, field, value)


def paginate(
    session: Session,
    statement: Select[tuple[ModelT]],
    *,
    schema: type[SchemaT],
    page: int,
    page_size: int,
) -> Page[SchemaT]:
    """Execute one filtered statement and return a typed page."""
    total_statement = select(func.count()).select_from(
        statement.order_by(None).subquery()
    )
    total = session.scalar(total_statement) or 0
    rows = session.scalars(
        statement.offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [schema.model_validate(row) for row in rows]  # type: ignore[attr-defined]
    return Page[SchemaT](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


def serialize_worker_ids(value: list[uuid.UUID] | None) -> list[str] | None:
    """Convert API UUIDs to JSON-safe values stored by Service."""
    if value is None:
        return None
    return [str(worker_id) for worker_id in value]


def set_values(instance: object, values: dict[str, Any]) -> None:
    """Assign a preprocessed dictionary to one ORM object."""
    for field, value in values.items():
        setattr(instance, field, value)
