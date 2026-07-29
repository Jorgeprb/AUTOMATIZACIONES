"""Tenant-safe customer helpers and E.164 normalization."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import phonenumbers
from fastapi import HTTPException, status
from phonenumbers.phonenumberutil import NumberParseException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClinicCustomerFieldDefinition, Worker

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")


def normalize_phone_e164(value: str, *, default_region: str = "ES") -> str:
    """Normalize an international or national telephone number to E.164."""
    raw = value.strip()
    if not raw:
        raise ValueError("El teléfono es obligatorio.")
    try:
        parsed = phonenumbers.parse(
            raw, None if raw.startswith("+") else default_region
        )
    except NumberParseException as exc:
        raise ValueError("El teléfono no tiene un formato válido.") from exc
    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(
        parsed
    ):
        raise ValueError("El teléfono no es válido.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_optional_phone(
    value: str | None, *, default_region: str = "ES"
) -> str | None:
    if value is None or not value.strip():
        return None
    return normalize_phone_e164(value, default_region=default_region)


def normalize_customer_phone(value: str, *, default_region: str = "ES") -> str:
    """Backward-compatible CRM phone normalizer used by voice and booking flows."""
    return normalize_phone_e164(value, default_region=default_region)


def validate_custom_values(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Validate customer custom values against active clinic definitions."""
    definitions = list(
        session.scalars(
            select(ClinicCustomerFieldDefinition)
            .where(
                ClinicCustomerFieldDefinition.clinic_id == clinic_id,
                ClinicCustomerFieldDefinition.is_active.is_(True),
            )
            .order_by(ClinicCustomerFieldDefinition.sort_order)
        )
    )
    by_key = {item.key: item for item in definitions}
    unknown = sorted(set(values) - set(by_key))
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Campos personalizados no permitidos: {', '.join(unknown)}.",
        )
    normalized: dict[str, Any] = {}
    for definition in definitions:
        value = values.get(definition.key)
        if value in (None, ""):
            if definition.required:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"El campo {definition.label} es obligatorio.",
                )
            continue
        try:
            if definition.field_type in {"text", "textarea"}:
                normalized[definition.key] = str(value).strip()
            elif definition.field_type == "number":
                normalized[definition.key] = str(Decimal(str(value)))
            elif definition.field_type == "boolean":
                if isinstance(value, bool):
                    normalized[definition.key] = value
                elif str(value).casefold() in {"true", "1", "yes", "sí", "si"}:
                    normalized[definition.key] = True
                elif str(value).casefold() in {"false", "0", "no"}:
                    normalized[definition.key] = False
                else:
                    raise ValueError
            elif definition.field_type == "date":
                normalized[definition.key] = date.fromisoformat(str(value)).isoformat()
            elif definition.field_type == "select":
                candidate = str(value)
                if candidate not in definition.options_json:
                    raise ValueError
                normalized[definition.key] = candidate
            else:
                raise ValueError
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Valor inválido para {definition.label}.",
            ) from exc
    return normalized


def validate_field_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not _KEY_RE.fullmatch(normalized):
        raise ValueError("La clave debe usar minúsculas, números y guion bajo.")
    return normalized


def validate_preferred_worker(
    session: Session,
    *,
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID | None,
) -> None:
    if worker_id is None:
        return
    exists = session.scalar(
        select(Worker.id).where(Worker.id == worker_id, Worker.clinic_id == clinic_id)
    )
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El profesional preferido no pertenece a la clínica.",
        )


def touch_contact_times(
    *,
    first_contact_at: datetime | None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    return first_contact_at or current, current
