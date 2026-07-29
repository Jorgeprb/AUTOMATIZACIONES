"""Shared resolution of clinic and worker weekly schedules."""

from __future__ import annotations

from typing import Any

from app.models import Worker


def _has_configured_ranges(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return any(isinstance(ranges, list) and bool(ranges) for ranges in value.values())


def effective_worker_hours(worker: Worker) -> dict[str, Any]:
    """Return clinic hours when inherited, otherwise the worker override."""
    if worker.inherit_clinic_hours:
        clinic_hours = getattr(worker.clinic, "opening_hours_json", None)
        if _has_configured_ranges(clinic_hours):
            return dict(clinic_hours)
    return dict(worker.working_hours_json or {})
