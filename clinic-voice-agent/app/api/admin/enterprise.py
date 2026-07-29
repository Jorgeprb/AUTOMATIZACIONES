"""Tenant-scoped CRM, resources, analytics, catalog and provisioning APIs."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.admin.common import clinic_or_404, commit_or_conflict, nested_or_404
from app.auth import AdminPrincipal
from app.customer_service import (
    normalize_customer_phone,
    validate_custom_values,
    validate_preferred_worker,
)
from app.db import get_db
from app.enterprise_schemas import (
    BillingPricePayload,
    BillingPriceRead,
    BillingProductPayload,
    BillingProductRead,
    ClinicAnalyticsResponse,
    ClinicCustomerPayload,
    ClinicCustomerRead,
    ClinicCustomerUpdate,
    CustomerDetail,
    CustomerFieldDefinitionPayload,
    CustomerFieldDefinitionRead,
    CustomerImportResult,
    CustomerMergeRequest,
    GlobalAnalyticsResponse,
    MetricPoint,
    ProvisioningRead,
    ProvisioningUpdate,
    RelatedAppointmentRead,
    RelatedCallRead,
    ResourcePayload,
    ResourceRead,
    ResourceRequirementPayload,
)
from app.enterprise_service import enqueue_outbox
from app.models import (
    Appointment,
    AppointmentStatus,
    BillingPrice,
    BillingProduct,
    CallAnalysis,
    CallSession,
    Clinic,
    ClinicCustomer,
    ClinicCustomerFieldDefinition,
    ClinicResource,
    ClinicSubscription,
    PaymentRecord,
    PhoneNumber,
    PhoneProvisioningOrder,
    ResourceReservation,
    Service,
    ServiceResourceRequirement,
    Worker,
)
from app.utils.security import require_admin_access

router = APIRouter(tags=["Admin · Enterprise"])


def _require_super(principal: AdminPrincipal) -> None:
    if not principal.is_super_admin:
        raise HTTPException(status_code=403, detail="Global administrator required.")


def _customer_read(row: ClinicCustomer) -> ClinicCustomerRead:
    return ClinicCustomerRead.model_validate(row)


def _definitions(
    session: Session, clinic_id: uuid.UUID
) -> list[ClinicCustomerFieldDefinition]:
    return list(
        session.scalars(
            select(ClinicCustomerFieldDefinition)
            .where(ClinicCustomerFieldDefinition.clinic_id == clinic_id)
            .order_by(
                ClinicCustomerFieldDefinition.sort_order,
                ClinicCustomerFieldDefinition.label,
            )
        )
    )


@router.get(
    "/admin/clinics/{clinic_id}/customers", response_model=list[ClinicCustomerRead]
)
def list_customers(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    search: str | None = None,
    active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> list[ClinicCustomerRead]:
    clinic_or_404(session, clinic_id)
    query = select(ClinicCustomer).where(ClinicCustomer.clinic_id == clinic_id)
    if search:
        token = f"%{search.strip()}%"
        query = query.where(
            or_(
                ClinicCustomer.name.ilike(token),
                ClinicCustomer.normalized_phone.ilike(token),
                ClinicCustomer.display_phone.ilike(token),
                ClinicCustomer.email.ilike(token),
            )
        )
    if active is not None:
        query = query.where(ClinicCustomer.is_active.is_(active))
    rows = session.scalars(
        query.order_by(
            ClinicCustomer.last_contact_at.desc().nullslast(), ClinicCustomer.name
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_customer_read(row) for row in rows]


@router.get("/admin/clinics/{clinic_id}/customers/export.csv")
def export_customers(
    clinic_id: uuid.UUID, session: Annotated[Session, Depends(get_db)]
) -> Response:
    clinic_or_404(session, clinic_id)
    definitions = _definitions(session, clinic_id)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "name",
            "phone",
            "email",
            "notes",
            "personalization_enabled",
            "is_active",
            *[d.key for d in definitions],
        ],
    )
    writer.writeheader()
    for customer in session.scalars(
        select(ClinicCustomer)
        .where(ClinicCustomer.clinic_id == clinic_id)
        .order_by(ClinicCustomer.name)
    ):
        row = {
            "name": customer.name,
            "phone": customer.display_phone,
            "email": customer.email or "",
            "notes": customer.notes or "",
            "personalization_enabled": customer.personalization_enabled,
            "is_active": customer.is_active,
        }
        row.update(
            {
                definition.key: customer.custom_values_json.get(definition.key, "")
                for definition in definitions
            }
        )
        writer.writerow(row)
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="clientes-{clinic_id}.csv"'
        },
    )


@router.post(
    "/admin/clinics/{clinic_id}/customers/import.csv",
    response_model=CustomerImportResult,
)
def import_customers(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> CustomerImportResult:
    clinic_or_404(session, clinic_id)
    raw = file.file.read(5_000_001)
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=413, detail="CSV file is too large.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must use UTF-8.") from exc
    definitions = _definitions(session, clinic_id)
    definition_keys = {d.key for d in definitions}
    created = updated = skipped = 0
    errors: list[str] = []
    for line_number, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            name = str(row.get("name") or "").strip()
            phone = str(row.get("phone") or "").strip()
            if not name or not phone:
                raise ValueError("name and phone are required")
            normalized = normalize_customer_phone(phone)
            values = {
                key: row.get(key)
                for key in definition_keys
                if row.get(key) not in (None, "")
            }
            values = validate_custom_values(session, clinic_id=clinic_id, values=values)
            existing = session.scalar(
                select(ClinicCustomer).where(
                    ClinicCustomer.clinic_id == clinic_id,
                    ClinicCustomer.normalized_phone == normalized,
                )
            )
            if existing is None:
                session.add(
                    ClinicCustomer(
                        clinic_id=clinic_id,
                        name=name,
                        normalized_phone=normalized,
                        display_phone=phone,
                        email=(str(row.get("email") or "").strip().casefold() or None),
                        notes=(str(row.get("notes") or "").strip() or None),
                        custom_values_json=values,
                        personalization_enabled=str(
                            row.get("personalization_enabled", "true")
                        ).casefold()
                        not in {"false", "0", "no"},
                        is_active=str(row.get("is_active", "true")).casefold()
                        not in {"false", "0", "no"},
                    )
                )
                created += 1
            else:
                existing.name = name
                existing.display_phone = phone
                existing.email = (
                    str(row.get("email") or "").strip().casefold() or existing.email
                )
                existing.notes = str(row.get("notes") or "").strip() or existing.notes
                existing.custom_values_json = {**existing.custom_values_json, **values}
                updated += 1
        except Exception as exc:
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Fila {line_number}: {exc}")
    commit_or_conflict(session, detail="CSV contains duplicate or invalid customers.")
    return CustomerImportResult(
        created=created, updated=updated, skipped=skipped, errors=errors
    )


@router.get(
    "/admin/clinics/{clinic_id}/customers/{customer_id}", response_model=CustomerDetail
)
def get_customer(
    clinic_id: uuid.UUID,
    customer_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CustomerDetail:
    customer = nested_or_404(
        session,
        ClinicCustomer,
        clinic_id=clinic_id,
        resource_id=customer_id,
        label="Customer",
    )
    appointments = session.scalars(
        select(Appointment)
        .where(
            Appointment.clinic_id == clinic_id, Appointment.customer_id == customer.id
        )
        .order_by(Appointment.start_at.desc())
        .limit(200)
    ).all()
    calls = session.scalars(
        select(CallSession)
        .where(
            CallSession.clinic_id == clinic_id, CallSession.customer_id == customer.id
        )
        .order_by(CallSession.started_at.desc())
        .limit(200)
    ).all()
    return CustomerDetail(
        **_customer_read(customer).model_dump(),
        appointments=[
            RelatedAppointmentRead.model_validate(item) for item in appointments
        ],
        calls=[RelatedCallRead.model_validate(item) for item in calls],
    )


@router.post(
    "/admin/clinics/{clinic_id}/customers",
    response_model=ClinicCustomerRead,
    status_code=201,
)
def create_customer(
    clinic_id: uuid.UUID,
    payload: ClinicCustomerPayload,
    session: Annotated[Session, Depends(get_db)],
) -> ClinicCustomerRead:
    clinic_or_404(session, clinic_id)
    normalized = normalize_customer_phone(payload.phone)
    values = validate_custom_values(
        session, clinic_id=clinic_id, values=payload.custom_values_json
    )
    validate_preferred_worker(
        session, clinic_id=clinic_id, worker_id=payload.preferred_worker_id
    )
    customer = ClinicCustomer(
        clinic_id=clinic_id,
        name=payload.name.strip(),
        normalized_phone=normalized,
        display_phone=payload.phone.strip(),
        email=payload.email.strip().casefold() if payload.email else None,
        notes=payload.notes,
        custom_values_json=values,
        preferred_worker_id=payload.preferred_worker_id,
        personalization_enabled=payload.personalization_enabled,
        is_active=payload.is_active,
    )
    session.add(customer)
    commit_or_conflict(
        session, detail="A customer with this phone already exists in the clinic."
    )
    session.refresh(customer)
    return _customer_read(customer)


@router.patch(
    "/admin/clinics/{clinic_id}/customers/{customer_id}",
    response_model=ClinicCustomerRead,
)
def update_customer(
    clinic_id: uuid.UUID,
    customer_id: uuid.UUID,
    payload: ClinicCustomerUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> ClinicCustomerRead:
    customer = nested_or_404(
        session,
        ClinicCustomer,
        clinic_id=clinic_id,
        resource_id=customer_id,
        label="Customer",
    )
    values = payload.model_dump(exclude_unset=True)
    if "phone" in values and values["phone"] is not None:
        customer.normalized_phone = normalize_customer_phone(values.pop("phone"))
        customer.display_phone = (
            payload.phone.strip() if payload.phone else customer.display_phone
        )
    if "custom_values_json" in values and values["custom_values_json"] is not None:
        values["custom_values_json"] = validate_custom_values(
            session,
            clinic_id=clinic_id,
            values=values["custom_values_json"],
        )
    if "preferred_worker_id" in values:
        validate_preferred_worker(
            session, clinic_id=clinic_id, worker_id=values["preferred_worker_id"]
        )
    for key, value in values.items():
        setattr(customer, key, value)
    commit_or_conflict(
        session, detail="A customer with this phone already exists in the clinic."
    )
    session.refresh(customer)
    return _customer_read(customer)


@router.post(
    "/admin/clinics/{clinic_id}/customers/{customer_id}/anonymize",
    response_model=ClinicCustomerRead,
)
def anonymize_customer(
    clinic_id: uuid.UUID,
    customer_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> ClinicCustomerRead:
    customer = nested_or_404(
        session,
        ClinicCustomer,
        clinic_id=clinic_id,
        resource_id=customer_id,
        label="Customer",
    )
    customer.name = "Cliente anonimizado"
    customer.normalized_phone = customer.id.hex
    customer.display_phone = "Anonimizado"
    customer.email = None
    customer.notes = None
    customer.custom_values_json = {}
    customer.preferred_worker_id = None
    customer.personalization_enabled = False
    customer.is_active = False
    customer.anonymized_at = datetime.now(UTC)
    session.commit()
    session.refresh(customer)
    return _customer_read(customer)


@router.delete("/admin/clinics/{clinic_id}/customers/{customer_id}", status_code=204)
def delete_customer(
    clinic_id: uuid.UUID,
    customer_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    customer = nested_or_404(
        session,
        ClinicCustomer,
        clinic_id=clinic_id,
        resource_id=customer_id,
        label="Customer",
    )
    related = (
        session.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.customer_id == customer.id
            )
        )
        or 0
    )
    related += (
        session.scalar(
            select(func.count(CallSession.id)).where(
                CallSession.customer_id == customer.id
            )
        )
        or 0
    )
    if related:
        anonymize_customer(clinic_id, customer_id, session)
        return
    session.delete(customer)
    session.commit()


@router.post(
    "/admin/clinics/{clinic_id}/customers/merge", response_model=ClinicCustomerRead
)
def merge_customers(
    clinic_id: uuid.UUID,
    payload: CustomerMergeRequest,
    session: Annotated[Session, Depends(get_db)],
) -> ClinicCustomerRead:
    if payload.source_customer_id == payload.target_customer_id:
        raise HTTPException(status_code=422, detail="Source and target must differ.")
    source = nested_or_404(
        session,
        ClinicCustomer,
        clinic_id=clinic_id,
        resource_id=payload.source_customer_id,
        label="Source customer",
    )
    target = nested_or_404(
        session,
        ClinicCustomer,
        clinic_id=clinic_id,
        resource_id=payload.target_customer_id,
        label="Target customer",
    )
    session.execute(
        update(Appointment)
        .where(Appointment.clinic_id == clinic_id, Appointment.customer_id == source.id)
        .values(customer_id=target.id)
    )
    session.execute(
        update(CallSession)
        .where(CallSession.clinic_id == clinic_id, CallSession.customer_id == source.id)
        .values(customer_id=target.id)
    )
    target.custom_values_json = {
        **source.custom_values_json,
        **target.custom_values_json,
    }
    target.notes = "\n".join(part for part in (target.notes, source.notes) if part)
    target.first_contact_at = min(
        filter(None, (target.first_contact_at, source.first_contact_at)), default=None
    )
    target.last_contact_at = max(
        filter(None, (target.last_contact_at, source.last_contact_at)), default=None
    )
    if target.preferred_worker_id is None:
        target.preferred_worker_id = source.preferred_worker_id
    session.delete(source)
    session.commit()
    session.refresh(target)
    return _customer_read(target)


@router.get(
    "/admin/clinics/{clinic_id}/customer-fields",
    response_model=list[CustomerFieldDefinitionRead],
)
def list_customer_fields(
    clinic_id: uuid.UUID, session: Annotated[Session, Depends(get_db)]
) -> list[CustomerFieldDefinitionRead]:
    clinic_or_404(session, clinic_id)
    return [
        CustomerFieldDefinitionRead.model_validate(row)
        for row in _definitions(session, clinic_id)
    ]


@router.post(
    "/admin/clinics/{clinic_id}/customer-fields",
    response_model=CustomerFieldDefinitionRead,
    status_code=201,
)
def create_customer_field(
    clinic_id: uuid.UUID,
    payload: CustomerFieldDefinitionPayload,
    session: Annotated[Session, Depends(get_db)],
) -> CustomerFieldDefinitionRead:
    clinic_or_404(session, clinic_id)
    row = ClinicCustomerFieldDefinition(clinic_id=clinic_id, **payload.model_dump())
    session.add(row)
    commit_or_conflict(session, detail="A custom field with this key already exists.")
    session.refresh(row)
    return CustomerFieldDefinitionRead.model_validate(row)


@router.patch(
    "/admin/clinics/{clinic_id}/customer-fields/{field_id}",
    response_model=CustomerFieldDefinitionRead,
)
def update_customer_field(
    clinic_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: CustomerFieldDefinitionPayload,
    session: Annotated[Session, Depends(get_db)],
) -> CustomerFieldDefinitionRead:
    row = nested_or_404(
        session,
        ClinicCustomerFieldDefinition,
        clinic_id=clinic_id,
        resource_id=field_id,
        label="Customer field",
    )
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    commit_or_conflict(session)
    session.refresh(row)
    return CustomerFieldDefinitionRead.model_validate(row)


@router.delete("/admin/clinics/{clinic_id}/customer-fields/{field_id}", status_code=204)
def delete_customer_field(
    clinic_id: uuid.UUID,
    field_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    row = nested_or_404(
        session,
        ClinicCustomerFieldDefinition,
        clinic_id=clinic_id,
        resource_id=field_id,
        label="Customer field",
    )
    session.delete(row)
    session.commit()


@router.get("/admin/clinics/{clinic_id}/resources", response_model=list[ResourceRead])
def list_resources(
    clinic_id: uuid.UUID, session: Annotated[Session, Depends(get_db)]
) -> list[ResourceRead]:
    clinic_or_404(session, clinic_id)
    return [
        ResourceRead.model_validate(row)
        for row in session.scalars(
            select(ClinicResource)
            .where(ClinicResource.clinic_id == clinic_id)
            .order_by(ClinicResource.name)
        )
    ]


@router.post(
    "/admin/clinics/{clinic_id}/resources", response_model=ResourceRead, status_code=201
)
def create_resource(
    clinic_id: uuid.UUID,
    payload: ResourcePayload,
    session: Annotated[Session, Depends(get_db)],
) -> ResourceRead:
    clinic_or_404(session, clinic_id)
    row = ClinicResource(clinic_id=clinic_id, **payload.model_dump())
    session.add(row)
    commit_or_conflict(session)
    session.refresh(row)
    return ResourceRead.model_validate(row)


@router.patch(
    "/admin/clinics/{clinic_id}/resources/{resource_id}", response_model=ResourceRead
)
def update_resource(
    clinic_id: uuid.UUID,
    resource_id: uuid.UUID,
    payload: ResourcePayload,
    session: Annotated[Session, Depends(get_db)],
) -> ResourceRead:
    row = nested_or_404(
        session,
        ClinicResource,
        clinic_id=clinic_id,
        resource_id=resource_id,
        label="Resource",
    )
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    commit_or_conflict(session)
    session.refresh(row)
    return ResourceRead.model_validate(row)


@router.delete("/admin/clinics/{clinic_id}/resources/{resource_id}", status_code=204)
def delete_resource(
    clinic_id: uuid.UUID,
    resource_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    row = nested_or_404(
        session,
        ClinicResource,
        clinic_id=clinic_id,
        resource_id=resource_id,
        label="Resource",
    )
    if session.scalar(
        select(func.count(ResourceReservation.id)).where(
            ResourceReservation.resource_id == row.id
        )
    ):
        row.is_active = False
    else:
        session.delete(row)
    session.commit()


@router.get(
    "/admin/clinics/{clinic_id}/services/{service_id}/resource-requirements",
    response_model=list[ResourceRequirementPayload],
)
def list_requirements(
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> list[ResourceRequirementPayload]:
    service = nested_or_404(
        session, Service, clinic_id=clinic_id, resource_id=service_id, label="Service"
    )
    return [
        ResourceRequirementPayload(resource_id=row.resource_id, quantity=row.quantity)
        for row in session.scalars(
            select(ServiceResourceRequirement).where(
                ServiceResourceRequirement.service_id == service.id
            )
        )
    ]


@router.put(
    "/admin/clinics/{clinic_id}/services/{service_id}/resource-requirements",
    response_model=list[ResourceRequirementPayload],
)
def replace_requirements(
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
    payload: list[ResourceRequirementPayload],
    session: Annotated[Session, Depends(get_db)],
) -> list[ResourceRequirementPayload]:
    service = nested_or_404(
        session, Service, clinic_id=clinic_id, resource_id=service_id, label="Service"
    )
    resource_ids = {item.resource_id for item in payload}
    if len(resource_ids) != len(payload):
        raise HTTPException(
            status_code=422,
            detail="A resource requirement cannot be repeated.",
        )
    found = (
        set(
            session.scalars(
                select(ClinicResource.id).where(
                    ClinicResource.clinic_id == clinic_id,
                    ClinicResource.id.in_(resource_ids),
                )
            )
        )
        if resource_ids
        else set()
    )
    if found != resource_ids:
        raise HTTPException(
            status_code=422,
            detail="One or more resources do not belong to this clinic.",
        )
    session.execute(
        delete(ServiceResourceRequirement).where(
            ServiceResourceRequirement.service_id == service.id
        )
    )
    for item in payload:
        session.add(
            ServiceResourceRequirement(
                clinic_id=clinic_id,
                service_id=service.id,
                resource_id=item.resource_id,
                quantity=item.quantity,
            )
        )
    session.commit()
    return payload


def _period(
    clinic: Clinic, period: str, date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    zone = ZoneInfo(clinic.timezone)
    now = datetime.now(zone)
    if date_from and date_to:
        return date_from.astimezone(UTC), date_to.astimezone(UTC)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=7)
    return start.astimezone(UTC), now.astimezone(UTC)


@router.get(
    "/admin/clinics/{clinic_id}/analytics", response_model=ClinicAnalyticsResponse
)
def clinic_analytics(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    period: str = "7d",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    worker_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    phone_number: str | None = None,
    appointment_status: str | None = None,
) -> ClinicAnalyticsResponse:
    clinic = clinic_or_404(session, clinic_id)
    start, end = _period(clinic, period, date_from, date_to)
    aq = select(Appointment).where(
        Appointment.clinic_id == clinic_id,
        Appointment.created_at >= start,
        Appointment.created_at <= end,
    )
    if worker_id:
        aq = aq.where(Appointment.worker_id == worker_id)
    if service_id:
        aq = aq.where(Appointment.service_id == service_id)
    if phone_number:
        aq = aq.where(Appointment.patient_phone.ilike(f"%{phone_number}%"))
    if appointment_status:
        aq = aq.where(Appointment.status == appointment_status)
    appointments = list(session.scalars(aq))
    calls = list(
        session.scalars(
            select(CallSession).where(
                CallSession.clinic_id == clinic_id,
                CallSession.started_at >= start,
                CallSession.started_at <= end,
            )
        )
    )
    service_names: dict[uuid.UUID, str] = dict(
        session.execute(
            select(Service.id, Service.name).where(Service.clinic_id == clinic_id)
        ).tuples()
    )
    worker_names: dict[uuid.UUID, str] = dict(
        session.execute(
            select(Worker.id, Worker.name).where(Worker.clinic_id == clinic_id)
        ).tuples()
    )
    analyses = list(
        session.scalars(
            select(CallAnalysis).where(
                CallAnalysis.clinic_id == clinic_id,
                CallAnalysis.created_at >= start,
                CallAnalysis.created_at <= end,
            )
        )
    )

    def points(counter: dict[str, int]) -> list[MetricPoint]:
        return [
            MetricPoint(key=k, label=k, value=float(v))
            for k, v in sorted(counter.items())
        ]

    def count_by(values: list[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        for value in values:
            result[value] = result.get(value, 0) + 1
        return result

    cancelled = sum(a.status == AppointmentStatus.CANCELLED for a in appointments)
    completed = sum(a.status == AppointmentStatus.COMPLETED for a in appointments)
    no_show = sum(a.status == AppointmentStatus.NO_SHOW for a in appointments)
    estimated = sum(
        int((service.price_amount or 0) * 100)
        for a in appointments
        if a.status != AppointmentStatus.CANCELLED
        and a.service_id
        and (service := session.get(Service, a.service_id)) is not None
    )
    booked_calls = len({a.call_session_id for a in appointments if a.call_session_id})
    durations = [
        (c.ended_at - c.started_at).total_seconds() for c in calls if c.ended_at
    ]
    new_customers = (
        session.scalar(
            select(func.count(ClinicCustomer.id)).where(
                ClinicCustomer.clinic_id == clinic_id,
                ClinicCustomer.created_at >= start,
                ClinicCustomer.created_at <= end,
            )
        )
        or 0
    )
    recurring = len({a.customer_id for a in appointments if a.customer_id}) - int(
        new_customers
    )
    service_counter = count_by(
        [
            service_names.get(a.service_id, "Sin servicio")
            if a.service_id
            else "Sin servicio"
            for a in appointments
        ]
    )
    worker_counter = count_by(
        [worker_names.get(a.worker_id, "Sin profesional") for a in appointments]
    )
    status_counter = count_by(
        [
            str(a.status.value if hasattr(a.status, "value") else a.status)
            for a in appointments
        ]
    )
    weekday_counter = count_by(
        [
            a.start_at.astimezone(ZoneInfo(clinic.timezone)).strftime("%A")
            for a in appointments
        ]
    )
    hour_counter = count_by(
        [
            f"{a.start_at.astimezone(ZoneInfo(clinic.timezone)).hour:02d}:00"
            for a in appointments
        ]
    )
    timeline_counter = count_by(
        [
            a.start_at.astimezone(ZoneInfo(clinic.timezone)).date().isoformat()
            for a in appointments
        ]
    )
    sentiment_counter = count_by([a.sentiment_label for a in analyses])
    heat = count_by(
        [
            f"{a.start_at.astimezone(ZoneInfo(clinic.timezone)).weekday()}:{a.start_at.astimezone(ZoneInfo(clinic.timezone)).hour}"
            for a in appointments
        ]
    )
    return ClinicAnalyticsResponse(
        appointments_created=len(appointments),
        appointments_cancelled=cancelled,
        appointments_completed=completed,
        appointments_no_show=no_show,
        cancellation_rate=cancelled / len(appointments) if appointments else 0,
        call_to_booking_conversion=booked_calls / len(calls) if calls else 0,
        estimated_revenue_minor=estimated,
        calls_answered=len(calls),
        calls_failed=sum(
            str(c.status.value if hasattr(c.status, "value") else c.status) == "failed"
            for c in calls
        ),
        average_call_duration_seconds=sum(durations) / len(durations)
        if durations
        else 0,
        new_customers=int(new_customers),
        returning_customers=max(0, recurring),
        appointments_by_service=points(service_counter),
        appointments_by_worker=points(worker_counter),
        appointments_by_weekday=points(weekday_counter),
        appointments_by_hour=points(hour_counter),
        appointment_statuses=points(status_counter),
        sentiments=points(sentiment_counter),
        timeline=points(timeline_counter),
        heatmap=[
            {
                "key": key,
                "value": value,
                "day": int(key.split(":")[0]),
                "hour": int(key.split(":")[1]),
            }
            for key, value in heat.items()
        ],
    )


@router.post("/admin/clinics/{clinic_id}/calls/{call_id}/reanalyze", status_code=202)
def reanalyze_call(
    clinic_id: uuid.UUID,
    call_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    call = nested_or_404(
        session, CallSession, clinic_id=clinic_id, resource_id=call_id, label="Call"
    )
    analysis = session.scalar(
        select(CallAnalysis).where(CallAnalysis.call_session_id == call.id)
    )
    if analysis is not None:
        analysis.error = None
        analysis.analyzed_at = None
    enqueue_outbox(
        session,
        kind="call_analysis.create",
        dedupe_key=f"call-analysis:{call.id}:manual:{uuid.uuid4()}",
        payload={"call_session_id": str(call.id)},
    )
    session.commit()
    return {"status": "queued"}


@router.get("/admin/analytics/global", response_model=GlobalAnalyticsResponse)
def global_analytics(
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> GlobalAnalyticsResponse:
    _require_super(principal)
    active_subs = (
        session.scalar(
            select(func.count(ClinicSubscription.id)).where(
                ClinicSubscription.status.in_(("active", "trialing"))
            )
        )
        or 0
    )
    mrr = (
        session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        BillingPrice.unit_amount_minor * ClinicSubscription.quantity
                    ),
                    0,
                )
            )
            .join(ClinicSubscription, ClinicSubscription.price_id == BillingPrice.id)
            .where(
                ClinicSubscription.status.in_(("active", "trialing")),
                BillingPrice.interval == "month",
            )
        )
        or 0
    )
    return GlobalAnalyticsResponse(
        clinics=session.scalar(select(func.count(Clinic.id))) or 0,
        contracted_numbers=session.scalar(select(func.count(PhoneNumber.id))) or 0,
        active_subscriptions=active_subs,
        mrr_minor=int(mrr),
        failed_payments=session.scalar(
            select(func.count(PaymentRecord.id)).where(PaymentRecord.status == "failed")
        )
        or 0,
        pending_provisioning=session.scalar(
            select(func.count(PhoneProvisioningOrder.id)).where(
                PhoneProvisioningOrder.status == "paid_pending_provisioning"
            )
        )
        or 0,
        appointments=session.scalar(select(func.count(Appointment.id))) or 0,
        calls=session.scalar(select(func.count(CallSession.id))) or 0,
    )


@router.get("/admin/billing/products", response_model=list[BillingProductRead])
def admin_products(
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> list[BillingProductRead]:
    _require_super(principal)
    return [
        BillingProductRead.model_validate(row)
        for row in session.scalars(select(BillingProduct).order_by(BillingProduct.name))
    ]


@router.post(
    "/admin/billing/products", response_model=BillingProductRead, status_code=201
)
def create_product(
    payload: BillingProductPayload,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> BillingProductRead:
    _require_super(principal)
    row = BillingProduct(**payload.model_dump())
    session.add(row)
    commit_or_conflict(session)
    session.refresh(row)
    return BillingProductRead.model_validate(row)


@router.patch("/admin/billing/products/{product_id}", response_model=BillingProductRead)
def update_product(
    product_id: uuid.UUID,
    payload: BillingProductPayload,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> BillingProductRead:
    _require_super(principal)
    row = session.get(BillingProduct, product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    commit_or_conflict(session)
    session.refresh(row)
    return BillingProductRead.model_validate(row)


@router.get("/admin/billing/prices", response_model=list[BillingPriceRead])
def admin_prices(
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> list[BillingPriceRead]:
    _require_super(principal)
    return [
        BillingPriceRead.model_validate(row)
        for row in session.scalars(select(BillingPrice).order_by(BillingPrice.code))
    ]


@router.post("/admin/billing/prices", response_model=BillingPriceRead, status_code=201)
def create_price(
    payload: BillingPricePayload,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> BillingPriceRead:
    _require_super(principal)
    if session.get(BillingProduct, payload.product_id) is None:
        raise HTTPException(status_code=422, detail="Product not found.")
    row = BillingPrice(**payload.model_dump())
    session.add(row)
    commit_or_conflict(session)
    session.refresh(row)
    return BillingPriceRead.model_validate(row)


@router.patch("/admin/billing/prices/{price_id}", response_model=BillingPriceRead)
def update_price(
    price_id: uuid.UUID,
    payload: BillingPricePayload,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> BillingPriceRead:
    _require_super(principal)
    row = session.get(BillingPrice, price_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Price not found.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    commit_or_conflict(session)
    session.refresh(row)
    return BillingPriceRead.model_validate(row)


@router.get("/admin/provisioning", response_model=list[ProvisioningRead])
def list_provisioning(
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> list[ProvisioningRead]:
    _require_super(principal)
    return [
        ProvisioningRead.model_validate(row)
        for row in session.scalars(
            select(PhoneProvisioningOrder).order_by(
                PhoneProvisioningOrder.created_at.desc()
            )
        )
    ]


@router.patch("/admin/provisioning/{order_id}", response_model=ProvisioningRead)
def update_provisioning(
    order_id: uuid.UUID,
    payload: ProvisioningUpdate,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> ProvisioningRead:
    _require_super(principal)
    row = session.get(PhoneProvisioningOrder, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Provisioning order not found.")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    now = datetime.now(UTC)
    if row.status == "provisioned" and row.provisioned_at is None:
        row.provisioned_at = now
    if row.status == "active":
        if not row.assigned_number:
            raise HTTPException(
                status_code=422, detail="Assigned number is required before activation."
            )
        row.activated_at = row.activated_at or now
        phone = session.scalar(
            select(PhoneNumber).where(PhoneNumber.phone_number == row.assigned_number)
        )
        if phone is None:
            phone = PhoneNumber(
                clinic_id=row.clinic_id,
                phone_number=row.assigned_number,
                provider=row.provider or "voip_studio",
                is_active=True,
            )
            session.add(phone)
        phone.clinic_id = row.clinic_id
        phone.is_active = True
        phone.provisioning_order_id = row.id
        phone.clinic_subscription_id = row.subscription_id
        phone.external_provider_id = row.external_provider_id
        from app.enterprise_service import upsert_entitlement

        upsert_entitlement(
            session,
            clinic_id=row.clinic_id,
            billing_account_id=row.billing_account_id,
            code="phone_number",
            status_value="active",
            quantity=row.quantity,
            subscription_id=row.subscription_id,
            starts_at=now,
            metadata={"phone_number": row.assigned_number},
        )
        enqueue_outbox(
            session,
            kind="email.send",
            dedupe_key=f"number-active:{row.id}",
            payload={
                "template": "number_activated",
                "provisioning_order_id": str(row.id),
            },
        )
    session.commit()
    session.refresh(row)
    return ProvisioningRead.model_validate(row)


@router.get("/admin/billing/accounts", response_model=list[dict])
def list_billing_accounts(
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> list[dict]:
    _require_super(principal)
    from app.models import AdminUser, BillingAccount

    rows = []
    for account in session.scalars(
        select(BillingAccount).order_by(BillingAccount.created_at.desc())
    ):
        owner = session.get(AdminUser, account.owner_user_id)
        clinics = list(
            session.execute(
                select(Clinic.id, Clinic.name).where(
                    Clinic.billing_account_id == account.id
                )
            )
        )
        subscriptions = list(
            session.scalars(
                select(ClinicSubscription).where(
                    ClinicSubscription.billing_account_id == account.id
                )
            )
        )
        provisioning = list(
            session.scalars(
                select(PhoneProvisioningOrder).where(
                    PhoneProvisioningOrder.billing_account_id == account.id
                )
            )
        )
        rows.append(
            {
                "id": str(account.id),
                "display_name": account.display_name,
                "billing_email": account.billing_email,
                "status": account.status,
                "owner": owner.email if owner else None,
                "clinics": [{"id": str(cid), "name": name} for cid, name in clinics],
                "subscriptions": [
                    {
                        "id": str(sub.id),
                        "clinic_id": str(sub.clinic_id),
                        "status": sub.status,
                        "quantity": sub.quantity,
                        "current_period_end": sub.current_period_end.isoformat()
                        if sub.current_period_end
                        else None,
                        "cancel_at_period_end": sub.cancel_at_period_end,
                    }
                    for sub in subscriptions
                ],
                "provisioning": [
                    {
                        "id": str(item.id),
                        "clinic_id": str(item.clinic_id),
                        "status": item.status,
                        "assigned_number": item.assigned_number,
                    }
                    for item in provisioning
                ],
            }
        )
    return rows


@router.get("/admin/clinics/{clinic_id}/commercial", response_model=dict)
def clinic_commercial_detail(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[AdminPrincipal, Depends(require_admin_access)],
) -> dict:
    _require_super(principal)
    clinic = clinic_or_404(session, clinic_id)
    if clinic.billing_account_id is None:
        return {
            "clinic_id": str(clinic.id),
            "billing_account": None,
            "subscriptions": [],
            "provisioning": [],
            "phone_numbers": [],
        }
    from app.models import AdminUser, BillingAccount

    account = session.get(BillingAccount, clinic.billing_account_id)
    owner = session.get(AdminUser, account.owner_user_id) if account else None
    subscriptions = list(
        session.scalars(
            select(ClinicSubscription).where(ClinicSubscription.clinic_id == clinic.id)
        )
    )
    provisioning = list(
        session.scalars(
            select(PhoneProvisioningOrder).where(
                PhoneProvisioningOrder.clinic_id == clinic.id
            )
        )
    )
    phone_numbers = list(
        session.scalars(select(PhoneNumber).where(PhoneNumber.clinic_id == clinic.id))
    )
    return {
        "clinic_id": str(clinic.id),
        "billing_account": (
            {
                "id": str(account.id),
                "display_name": account.display_name,
                "owner": owner.email if owner else None,
                "billing_email": account.billing_email,
                "status": account.status,
            }
            if account
            else None
        ),
        "subscriptions": [
            {
                "id": str(row.id),
                "status": row.status,
                "quantity": row.quantity,
                "current_period_end": row.current_period_end.isoformat()
                if row.current_period_end
                else None,
                "cancel_at_period_end": row.cancel_at_period_end,
            }
            for row in subscriptions
        ],
        "provisioning": [
            ProvisioningRead.model_validate(row).model_dump(mode="json")
            for row in provisioning
        ],
        "phone_numbers": [
            {
                "id": str(row.id),
                "number": row.phone_number,
                "provider": row.provider,
                "active": row.is_active,
            }
            for row in phone_numbers
        ],
    }
