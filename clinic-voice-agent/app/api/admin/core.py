"""CRUD endpoints for clinics and their operational resources."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import cast, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.admin_schemas import (
    AssistantConfigCreate,
    AssistantConfigRead,
    AssistantConfigUpdate,
    AssistantOptionRead,
    AssistantOptionsResponse,
    AssistantRecommendedTemplateResponse,
    AssistantVoicePreviewRequest,
    ClinicCreate,
    ClinicRead,
    ClinicUpdate,
    DeleteResponse,
    Page,
    PhoneNumberCreate,
    PhoneNumberRead,
    PhoneNumberUpdate,
    PromptPreviewResponse,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
    VoiceCatalogRead,
    VoiceProviderRead,
    VoiceProviderSyncResponse,
    WorkerCreate,
    WorkerRead,
    WorkerUpdate,
)
from app.api.admin.common import (
    apply_update,
    clinic_or_404,
    commit_or_conflict,
    nested_or_404,
    paginate,
    serialize_worker_ids,
    set_values,
)
from app.api.calendar import calendar_status, list_calendars
from app.api.workers import create_worker_calendar, link_worker_calendar
from app.audio import TTSGenerationError, synthesize_speech
from app.calendar.auth import (
    GoogleOAuthConfigurationError,
    create_google_authorization_request,
    diagnose_google_oauth_configuration,
)
from app.calendar.google_client import (
    GoogleAuthorizationRequired,
    get_authorized_calendar_client,
)
from app.calendar.scheduler import SchedulingError, query_freebusy
from app.call_audio import (
    normalize_call_audio_mode,
    requires_external_voice_legal_confirmation,
)
from app.config import Settings, get_settings
from app.db import get_db
from app.models import (
    AssistantConfig,
    Clinic,
    ConversationFlow,
    PhoneNumber,
    Service,
    VoiceCatalog,
    Worker,
)
from app.openai_realtime.prompt_builder import (
    build_clinic_context,
    build_realtime_instructions,
)
from app.schemas import (
    CalendarListResponse,
    CalendarStatusResponse,
    FreeBusyPeriodResponse,
    GoogleOAuthDiagnosticIssueResponse,
    GoogleOAuthDiagnosticResponse,
    GoogleOAuthStartUrlResponse,
    WorkerCalendarCreateRequest,
    WorkerCalendarLinkRequest,
    WorkerCalendarResponse,
    WorkerFreeBusyTestRequest,
    WorkerFreeBusyTestResponse,
)
from app.voice_profile import (
    build_voice_instruction_block,
    effective_preview_voice,
)
from app.voice_providers import list_voice_provider_info
from app.voice_providers.catalog import (
    ensure_voice_catalog_seeded,
    list_catalog_for_provider,
    sync_voice_catalog,
)

router = APIRouter(prefix="/admin")

VOICE_LABELS = {
    "marin": "Marin · recomendada por OpenAI",
    "cedar": "Cedar · recomendada por OpenAI",
    "alloy": "Alloy",
    "ash": "Ash",
    "ballad": "Ballad",
    "coral": "Coral",
    "echo": "Echo",
    "sage": "Sage",
    "shimmer": "Shimmer",
    "verse": "Verse",
}


def _validate_allowed_workers(
    session: Session,
    clinic_id: uuid.UUID,
    worker_ids: list[uuid.UUID] | None,
) -> None:
    """Ensure every service worker belongs to the same clinic."""
    if not worker_ids:
        return
    found = set(
        session.scalars(
            select(Worker.id).where(
                Worker.clinic_id == clinic_id,
                Worker.id.in_(worker_ids),
            )
        )
    )
    if found != set(worker_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Every allowed worker must belong to the clinic.",
        )


def _ensure_active_config_available(
    session: Session,
    clinic_id: uuid.UUID,
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Reject a second active assistant configuration."""
    statement = select(AssistantConfig.id).where(
        AssistantConfig.clinic_id == clinic_id,
        AssistantConfig.is_active.is_(True),
    )
    if exclude_id is not None:
        statement = statement.where(AssistantConfig.id != exclude_id)
    if session.scalar(statement) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The clinic already has an active assistant configuration.",
        )


def _validate_conversation_flow(
    session: Session,
    clinic_id: uuid.UUID,
    conversation_flow_id: uuid.UUID | None,
) -> None:
    """Ensure an assistant only references a flow from its own clinic."""
    if conversation_flow_id is None:
        return
    exists = session.scalar(
        select(ConversationFlow.id).where(
            ConversationFlow.id == conversation_flow_id,
            ConversationFlow.clinic_id == clinic_id,
        )
    )
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conversation flow must belong to the clinic.",
        )


def _assistant_config_values_for_create(
    payload: AssistantConfigCreate,
) -> dict[str, Any]:
    """Normalize assistant create payload before it reaches the ORM."""
    values = payload.model_dump()
    _enforce_assistant_voice_policy(values)
    return values


def _assistant_config_values_for_update(
    config: AssistantConfig,
    payload: AssistantConfigUpdate,
) -> dict[str, Any]:
    """Normalize partial assistant updates with existing persisted values."""
    values = payload.model_dump(exclude_unset=True)
    _enforce_assistant_voice_policy(values, current=config)
    return values


def _enforce_assistant_voice_policy(
    values: dict[str, Any],
    *,
    current: AssistantConfig | None = None,
) -> None:
    """Force VPS media bridge for external voices and guard custom voices."""
    voice_provider = str(
        values.get(
            "voice_provider",
            current.voice_provider if current is not None else "openai",
        )
    )
    requested_mode = str(
        values.get(
            "call_audio_mode",
            current.call_audio_mode
            if current is not None
            else "openai_hosted_sip",
        )
    )
    values["call_audio_mode"] = normalize_call_audio_mode(
        voice_provider=voice_provider,
        requested_mode=requested_mode,
    )
    legal_confirmed = bool(
        values.get(
            "external_voice_legal_confirmed",
            current.external_voice_legal_confirmed if current is not None else False,
        )
    )
    if (
        requires_external_voice_legal_confirmation(voice_provider)
        and not legal_confirmed
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "external_voice_legal_confirmed must be true for cloned or "
                "custom external voice providers."
            ),
        )


@router.get(
    "/clinics",
    response_model=Page[ClinicRead],
    tags=["Admin · Clinics"],
)
def list_clinics(
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> Page[ClinicRead]:
    """List clinics with simple pagination and active-state filtering."""
    statement = select(Clinic)
    if is_active is not None:
        statement = statement.where(Clinic.is_active.is_(is_active))
    return paginate(
        session,
        statement.order_by(Clinic.name, Clinic.id),
        schema=ClinicRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics",
    response_model=ClinicRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Clinics"],
)
def create_clinic(
    payload: ClinicCreate,
    session: Annotated[Session, Depends(get_db)],
) -> Clinic:
    """Create one tenant clinic."""
    clinic = Clinic(**payload.model_dump())
    session.add(clinic)
    commit_or_conflict(session, detail="The main phone number is already in use.")
    session.refresh(clinic)
    return clinic


@router.get(
    "/clinics/{clinic_id}",
    response_model=ClinicRead,
    tags=["Admin · Clinics"],
)
def get_clinic(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> Clinic:
    """Get one clinic."""
    return clinic_or_404(session, clinic_id)


@router.patch(
    "/clinics/{clinic_id}",
    response_model=ClinicRead,
    tags=["Admin · Clinics"],
)
def update_clinic(
    clinic_id: uuid.UUID,
    payload: ClinicUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> Clinic:
    """Partially update one clinic."""
    clinic = clinic_or_404(session, clinic_id)
    apply_update(clinic, payload)
    commit_or_conflict(session, detail="The main phone number is already in use.")
    session.refresh(clinic)
    return clinic


@router.delete(
    "/clinics/{clinic_id}",
    response_model=DeleteResponse,
    tags=["Admin · Clinics"],
)
def delete_clinic(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one clinic and its owned configuration."""
    clinic = clinic_or_404(session, clinic_id)
    session.delete(clinic)
    commit_or_conflict(
        session,
        detail="The clinic cannot be deleted while restricted records exist.",
    )
    return DeleteResponse(id=clinic_id)


@router.get(
    "/clinics/{clinic_id}/phone-numbers",
    response_model=Page[PhoneNumberRead],
    tags=["Admin · Phone numbers"],
)
def list_phone_numbers(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> Page[PhoneNumberRead]:
    """List telephone numbers owned by a clinic."""
    clinic_or_404(session, clinic_id)
    statement = select(PhoneNumber).where(PhoneNumber.clinic_id == clinic_id)
    if is_active is not None:
        statement = statement.where(PhoneNumber.is_active.is_(is_active))
    return paginate(
        session,
        statement.order_by(PhoneNumber.label, PhoneNumber.id),
        schema=PhoneNumberRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics/{clinic_id}/phone-numbers",
    response_model=PhoneNumberRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Phone numbers"],
)
def create_phone_number(
    clinic_id: uuid.UUID,
    payload: PhoneNumberCreate,
    session: Annotated[Session, Depends(get_db)],
) -> PhoneNumber:
    """Create one routed clinic number."""
    clinic_or_404(session, clinic_id)
    phone_number = PhoneNumber(clinic_id=clinic_id, **payload.model_dump())
    session.add(phone_number)
    commit_or_conflict(session, detail="The phone number is already registered.")
    session.refresh(phone_number)
    return phone_number


@router.get(
    "/clinics/{clinic_id}/phone-numbers/{phone_number_id}",
    response_model=PhoneNumberRead,
    tags=["Admin · Phone numbers"],
)
def get_phone_number(
    clinic_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> PhoneNumber:
    """Get one clinic phone number."""
    return nested_or_404(
        session,
        PhoneNumber,
        clinic_id=clinic_id,
        resource_id=phone_number_id,
        label="Phone number",
    )


@router.patch(
    "/clinics/{clinic_id}/phone-numbers/{phone_number_id}",
    response_model=PhoneNumberRead,
    tags=["Admin · Phone numbers"],
)
def update_phone_number(
    clinic_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    payload: PhoneNumberUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> PhoneNumber:
    """Partially update one clinic phone number."""
    phone_number = get_phone_number(clinic_id, phone_number_id, session)
    apply_update(phone_number, payload)
    commit_or_conflict(session, detail="The phone number is already registered.")
    session.refresh(phone_number)
    return phone_number


@router.delete(
    "/clinics/{clinic_id}/phone-numbers/{phone_number_id}",
    response_model=DeleteResponse,
    tags=["Admin · Phone numbers"],
)
def delete_phone_number(
    clinic_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one clinic phone number."""
    phone_number = get_phone_number(clinic_id, phone_number_id, session)
    session.delete(phone_number)
    commit_or_conflict(session)
    return DeleteResponse(id=phone_number_id)


@router.get(
    "/clinics/{clinic_id}/workers",
    response_model=Page[WorkerRead],
    tags=["Admin · Workers"],
)
def list_workers(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> Page[WorkerRead]:
    """List clinic workers."""
    clinic_or_404(session, clinic_id)
    statement = select(Worker).where(Worker.clinic_id == clinic_id)
    if is_active is not None:
        statement = statement.where(Worker.is_active.is_(is_active))
    return paginate(
        session,
        statement.order_by(Worker.name, Worker.id),
        schema=WorkerRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics/{clinic_id}/workers",
    response_model=WorkerRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Workers"],
)
def create_worker(
    clinic_id: uuid.UUID,
    payload: WorkerCreate,
    session: Annotated[Session, Depends(get_db)],
) -> Worker:
    """Create one clinic worker."""
    clinic_or_404(session, clinic_id)
    worker = Worker(clinic_id=clinic_id, **payload.model_dump())
    session.add(worker)
    commit_or_conflict(
        session,
        detail="This calendar is already linked to another clinic worker.",
    )
    session.refresh(worker)
    return worker


@router.get(
    "/clinics/{clinic_id}/workers/{worker_id}",
    response_model=WorkerRead,
    tags=["Admin · Workers"],
)
def get_worker(
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> Worker:
    """Get one clinic worker."""
    return nested_or_404(
        session,
        Worker,
        clinic_id=clinic_id,
        resource_id=worker_id,
        label="Worker",
    )


@router.patch(
    "/clinics/{clinic_id}/workers/{worker_id}",
    response_model=WorkerRead,
    tags=["Admin · Workers"],
)
def update_worker(
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    payload: WorkerUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> Worker:
    """Partially update one worker."""
    worker = get_worker(clinic_id, worker_id, session)
    apply_update(worker, payload)
    commit_or_conflict(
        session,
        detail="This calendar is already linked to another clinic worker.",
    )
    session.refresh(worker)
    return worker


@router.delete(
    "/clinics/{clinic_id}/workers/{worker_id}",
    response_model=DeleteResponse,
    tags=["Admin · Workers"],
)
def delete_worker(
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete a worker when no appointment restricts it."""
    worker = get_worker(clinic_id, worker_id, session)
    session.delete(worker)
    commit_or_conflict(
        session,
        detail="The worker has appointments and cannot be deleted.",
    )
    return DeleteResponse(id=worker_id)


@router.get(
    "/clinics/{clinic_id}/calendar-status",
    response_model=CalendarStatusResponse,
    tags=["Admin · Google Calendar"],
)
def get_admin_calendar_status(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CalendarStatusResponse:
    """Expose clinic Google connectivity to the administration panel."""
    return calendar_status(clinic_id, session, settings)


@router.get(
    "/clinics/{clinic_id}/google-oauth/diagnostics",
    response_model=GoogleOAuthDiagnosticResponse,
    tags=["Admin · Google Calendar"],
)
def get_admin_google_oauth_diagnostics(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleOAuthDiagnosticResponse:
    """Return safe Google OAuth configuration and connection diagnostics."""
    clinic_or_404(session, clinic_id)
    configuration = diagnose_google_oauth_configuration(settings)
    connected = False
    needs_reauthorization = False
    account_email: str | None = None
    status_payload: CalendarStatusResponse | None = None
    if configuration.can_start_oauth:
        status_payload = calendar_status(clinic_id, session, settings)
        connected = status_payload.connected
        needs_reauthorization = status_payload.needs_reauthorization
        account_email = status_payload.account_email
    return GoogleOAuthDiagnosticResponse(
        clinic_id=clinic_id,
        configured=configuration.configured,
        can_start_oauth=configuration.can_start_oauth,
        connected=connected,
        needs_reauthorization=needs_reauthorization,
        account_email=account_email,
        redirect_uri=configuration.redirect_uri,
        public_base_url=configuration.public_base_url,
        frontend_base_url=configuration.frontend_base_url,
        issues=[
            GoogleOAuthDiagnosticIssueResponse(
                variable=issue.variable,
                severity=issue.severity,
                message=issue.message,
                help=issue.help,
            )
            for issue in configuration.issues
        ],
    )


@router.get(
    "/clinics/{clinic_id}/google-oauth/start-url",
    response_model=GoogleOAuthStartUrlResponse,
    tags=["Admin · Google Calendar"],
)
def get_admin_google_oauth_start_url(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GoogleOAuthStartUrlResponse:
    """Return the Google authorization URL only when OAuth settings are valid."""
    clinic_or_404(session, clinic_id)
    try:
        authorization = create_google_authorization_request(settings, clinic_id)
    except GoogleOAuthConfigurationError as exc:
        variables = ", ".join(issue.variable for issue in exc.issues)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google OAuth is not configured correctly. Check: {variables}.",
        ) from exc
    return GoogleOAuthStartUrlResponse(
        clinic_id=clinic_id,
        authorization_url=authorization.authorization_url,
    )


@router.get(
    "/clinics/{clinic_id}/calendars",
    response_model=CalendarListResponse,
    tags=["Admin · Google Calendar"],
)
def list_admin_calendars(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CalendarListResponse:
    """List writable Google calendars and event colors for the panel."""
    return list_calendars(clinic_id, session, settings)


@router.post(
    "/clinics/{clinic_id}/workers/{worker_id}/create-calendar",
    response_model=WorkerCalendarResponse,
    tags=["Admin · Google Calendar"],
)
def create_admin_worker_calendar(
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: Annotated[
        WorkerCalendarCreateRequest | None,
        Body(),
    ] = None,
) -> WorkerCalendarResponse:
    """Create and link a Google secondary calendar for one worker."""
    get_worker(clinic_id, worker_id, session)
    return create_worker_calendar(worker_id, session, settings, payload)


@router.post(
    "/clinics/{clinic_id}/workers/{worker_id}/link-calendar",
    response_model=WorkerCalendarResponse,
    tags=["Admin · Google Calendar"],
)
def link_admin_worker_calendar(
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    payload: WorkerCalendarLinkRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkerCalendarResponse:
    """Link an existing writable Google calendar to one worker."""
    get_worker(clinic_id, worker_id, session)
    return link_worker_calendar(worker_id, payload, session, settings)


@router.post(
    "/clinics/{clinic_id}/workers/{worker_id}/test-freebusy",
    response_model=WorkerFreeBusyTestResponse,
    tags=["Admin · Google Calendar"],
)
def test_admin_worker_freebusy(
    clinic_id: uuid.UUID,
    worker_id: uuid.UUID,
    payload: WorkerFreeBusyTestRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkerFreeBusyTestResponse:
    """Query Google FreeBusy for one linked worker without creating an event."""
    worker = get_worker(clinic_id, worker_id, session)
    clinic = clinic_or_404(session, clinic_id)
    if not worker.calendar_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Worker does not have a linked calendar.",
        )
    try:
        client = get_authorized_calendar_client(session, settings, clinic_id)
        busy = query_freebusy(
            client,
            calendar_ids=[worker.calendar_id],
            time_min=payload.time_min,
            time_max=payload.time_max,
            timezone=clinic.timezone,
        )[worker.calendar_id]
    except GoogleAuthorizationRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except SchedulingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return WorkerFreeBusyTestResponse(
        worker_id=worker.id,
        calendar_id=worker.calendar_id,
        time_min=payload.time_min,
        time_max=payload.time_max,
        busy_ranges=[
            FreeBusyPeriodResponse(start_at=period.start, end_at=period.end)
            for period in busy
        ],
    )


@router.get(
    "/clinics/{clinic_id}/services",
    response_model=Page[ServiceRead],
    tags=["Admin · Services and prices"],
)
def list_services(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    worker_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[ServiceRead]:
    """List services and prices, optionally usable by one worker."""
    clinic_or_404(session, clinic_id)
    statement = select(Service).where(Service.clinic_id == clinic_id)
    if is_active is not None:
        statement = statement.where(Service.is_active.is_(is_active))
    if worker_id is not None:
        statement = statement.where(
            or_(
                Service.allowed_worker_ids.is_(None),
                cast(Service.allowed_worker_ids, JSONB).contains([str(worker_id)]),
            )
        )
    return paginate(
        session,
        statement.order_by(Service.name, Service.id),
        schema=ServiceRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics/{clinic_id}/services",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Services and prices"],
)
def create_service(
    clinic_id: uuid.UUID,
    payload: ServiceCreate,
    session: Annotated[Session, Depends(get_db)],
) -> Service:
    """Create one clinic service and its public price data."""
    clinic_or_404(session, clinic_id)
    _validate_allowed_workers(session, clinic_id, payload.allowed_worker_ids)
    values = payload.model_dump(exclude={"allowed_worker_ids"})
    values["allowed_worker_ids"] = serialize_worker_ids(payload.allowed_worker_ids)
    service = Service(clinic_id=clinic_id, **values)
    session.add(service)
    commit_or_conflict(session, detail="A service with this name already exists.")
    session.refresh(service)
    return service


@router.get(
    "/clinics/{clinic_id}/services/{service_id}",
    response_model=ServiceRead,
    tags=["Admin · Services and prices"],
)
def get_service(
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> Service:
    """Get one clinic service."""
    return nested_or_404(
        session,
        Service,
        clinic_id=clinic_id,
        resource_id=service_id,
        label="Service",
    )


@router.patch(
    "/clinics/{clinic_id}/services/{service_id}",
    response_model=ServiceRead,
    tags=["Admin · Services and prices"],
)
def update_service(
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> Service:
    """Partially update one clinic service."""
    service = get_service(clinic_id, service_id, session)
    supplied = payload.model_fields_set
    if "allowed_worker_ids" in supplied:
        _validate_allowed_workers(session, clinic_id, payload.allowed_worker_ids)
    values = payload.model_dump(exclude_unset=True, exclude={"allowed_worker_ids"})
    if "allowed_worker_ids" in supplied:
        values["allowed_worker_ids"] = serialize_worker_ids(payload.allowed_worker_ids)
    set_values(service, values)
    commit_or_conflict(session, detail="A service with this name already exists.")
    session.refresh(service)
    return service


@router.delete(
    "/clinics/{clinic_id}/services/{service_id}",
    response_model=DeleteResponse,
    tags=["Admin · Services and prices"],
)
def delete_service(
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one service; historical appointments keep a null service link."""
    service = get_service(clinic_id, service_id, session)
    session.delete(service)
    commit_or_conflict(session)
    return DeleteResponse(id=service_id)


@router.get(
    "/voice-providers",
    response_model=list[VoiceProviderRead],
    tags=["Admin · Voice providers"],
)
def list_admin_voice_providers(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[VoiceProviderRead]:
    """Return voice providers and whether their credentials are configured."""
    return [
        VoiceProviderRead(
            id=provider.id,
            display_name=provider.display_name,
            configured=provider.configured,
            supports_tts=provider.supports_tts,
            supports_streaming=provider.supports_streaming,
            supports_telephony_codec=provider.supports_telephony_codec,
            supports_stt=provider.supports_stt,
            supports_voice_clone=provider.supports_voice_clone,
            requires_consent=provider.requires_consent,
            recommended=provider.recommended,
            enabled=provider.enabled,
            notes=provider.notes,
        )
        for provider in list_voice_provider_info(settings)
    ]


@router.get(
    "/voice-providers/{provider}/voices",
    response_model=list[VoiceCatalogRead],
    tags=["Admin · Voice providers"],
)
def list_admin_provider_voices(
    provider: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[VoiceCatalog]:
    """Return synchronized voices for one provider."""
    try:
        return list_catalog_for_provider(session, settings, provider)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proveedor de voz no soportado: {provider}",
        ) from exc


@router.post(
    "/voice-providers/sync",
    response_model=VoiceProviderSyncResponse,
    tags=["Admin · Voice providers"],
)
def sync_admin_voice_providers(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VoiceProviderSyncResponse:
    """Sync static and official provider catalogs into the database."""
    synced = sync_voice_catalog(session, settings)
    return VoiceProviderSyncResponse(ok=True, synced=synced)


@router.get(
    "/assistant-options",
    response_model=AssistantOptionsResponse,
    tags=["Admin · Assistant configs"],
)
def get_assistant_options(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantOptionsResponse:
    """Return locally allowed models, official voices, and clinic languages."""
    ensure_voice_catalog_seeded(session, settings)
    return AssistantOptionsResponse(
        default_model=settings.openai_realtime_model,
        default_voice=settings.openai_realtime_voice,
        models=[
            AssistantOptionRead(
                id=model,
                label=model,
                recommended=model == settings.openai_realtime_model,
            )
            for model in settings.openai_realtime_model_list
        ],
        voices=[
            AssistantOptionRead(
                id=voice,
                label=VOICE_LABELS.get(voice, voice),
                recommended=voice in {"marin", "cedar"},
            )
            for voice in settings.openai_realtime_voice_list
        ],
        languages=[
            AssistantOptionRead(
                id="es",
                label="Español (genérico)",
            ),
            AssistantOptionRead(
                id="es-ES",
                label="Español de España",
                recommended=True,
            ),
            AssistantOptionRead(
                id="gl-ES",
                label="Galego",
            ),
            AssistantOptionRead(
                id="ca-ES",
                label="Català",
            ),
            AssistantOptionRead(
                id="eu-ES",
                label="Euskara",
            ),
            AssistantOptionRead(
                id="en",
                label="English",
            ),
        ],
        voice_providers=[
            VoiceProviderRead(
                id=provider.id,
                display_name=provider.display_name,
                configured=provider.configured,
                supports_tts=provider.supports_tts,
                supports_streaming=provider.supports_streaming,
                supports_telephony_codec=provider.supports_telephony_codec,
                supports_stt=provider.supports_stt,
                supports_voice_clone=provider.supports_voice_clone,
                requires_consent=provider.requires_consent,
                recommended=provider.recommended,
                enabled=provider.enabled,
                notes=provider.notes,
            )
            for provider in list_voice_provider_info(settings)
        ],
        output_audio_formats=["pcm16", "wav", "mp3", "opus"],
        telephony_codecs=["pcmu", "pcma", "pcm16"],
    )


@router.get(
    "/assistant-templates/recommended",
    response_model=AssistantRecommendedTemplateResponse,
    tags=["Admin · Assistant configs"],
)
def get_recommended_assistant_template() -> AssistantRecommendedTemplateResponse:
    """Return safe recommended assistant behavior defaults for MVP clinics."""
    return AssistantRecommendedTemplateResponse(
        first_message=(
            "Hola, soy el asistente virtual de la clínica. "
            "Puedo ayudarle con información y citas."
        ),
        system_prompt=(
            "Gestiona información administrativa, servicios y citas con respuestas "
            "breves, naturales y profesionales. No inventes precios, servicios, "
            "trabajadores ni huecos."
        ),
        safety_prompt=(
            "No diagnostiques ni recomiendes medicación. Ante una urgencia, dolor "
            "fuerte, dificultad respiratoria, pérdida de consciencia o sangrado "
            "grave, indica llamar al 112 o acudir a urgencias."
        ),
        booking_policy_prompt=(
            "Recoge datos mínimos, propone hasta tres huecos reales y reserva cuando "
            "la persona acepte un hueco de forma natural."
        ),
        cancellation_policy_prompt=(
            "Identifica la cita correcta y confirma con la persona antes de cancelarla."
        ),
        transfer_policy_prompt=(
            "Transfiere peticiones fuera de alcance, dudas clínicas "
            "o solicitud expresa."
        ),
        tone="profesional",
        response_length="normal",
        ask_patient_name=True,
        ask_patient_phone=True,
        ask_general_reason=True,
        allow_booking_without_worker=True,
        allow_bookings=True,
        allow_price_answers=True,
        ask_service=True,
        max_proposed_slots=3,
        max_consecutive_questions=2,
        conversation_style="natural",
        initiative_level="medio",
        commercial_call_handling="declinar",
        allow_cancellations=True,
        allow_reschedules=True,
        natural_confirmation_required=True,
        avoid_exact_confirmation_phrases=True,
        additional_instructions=(
            "Prioriza frases cortas y no pidas confirmaciones exactas."
        ),
        forbidden_phrases="Le diagnostico\nTome esta medicación",
        no_availability_message=(
            "No tengo huecos en esa franja. Le propongo otras opciones."
        ),
        missing_calendar_message=(
            "Falta enlazar el calendario del trabajador. Recepción debe revisarlo."
        ),
        emergency_message=(
            "Si es una urgencia médica, llame al 112 ahora o acuda a urgencias."
        ),
        human_transfer_message="Le paso con una persona si está disponible.",
        human_transfer_rules=(
            "Transfiere a humano si el usuario lo pide, si hay queja, si falta "
            "informaciÃ³n crÃ­tica o si la peticiÃ³n queda fuera de alcance."
        ),
        commercial_call_message=(
            "Gracias, pero este nÃºmero es para pacientes y gestiÃ³n de citas. "
            "No podemos atender llamadas comerciales por esta vÃ­a."
        ),
        conversation_extra_rules=(
            "No repitas preguntas ya respondidas. Usa pending_slots para "
            "interpretar 'la primera', 'esa' o una hora concreta."
        ),
        closing_message="Gracias por llamar. Hasta luego.",
        use_prices=True,
        use_knowledge_base=True,
        strict_calendar_mode=True,
    )


@router.post(
    "/clinics/{clinic_id}/assistant-configs/voice-preview",
    tags=["Admin · Assistant configs"],
)
def preview_assistant_voice(
    clinic_id: uuid.UUID,
    payload: AssistantVoicePreviewRequest,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Generate a finite voice preview without creating a conversation."""
    clinic_or_404(session, clinic_id)
    if payload.voice_provider == "openai":
        voice = effective_preview_voice(payload)
    else:
        voice = (
            payload.tts_preview_voice
            or payload.voice_id
            or payload.realtime_voice
        ).strip()
    instructions = build_voice_instruction_block(payload)
    try:
        result = synthesize_speech(
            settings,
            provider=payload.voice_provider,
            text=payload.text,
            voice=voice,
            model=payload.tts_model or payload.realtime_model,
            instructions=instructions,
            response_format=payload.preview_audio_format,
            output_audio_format=payload.output_audio_format,
            telephony_codec=payload.telephony_codec,
            locale=payload.voice_locale,
            gender=payload.voice_gender,
            provider_region=payload.azure_speech_region,
            voice_style=payload.voice_style,
            voice_speed=payload.voice_speed,
            voice_pitch=payload.voice_pitch,
            voice_stability=payload.voice_stability,
            voice_similarity=payload.voice_similarity,
            voice_temperature=payload.voice_temperature,
        )
    except TTSGenerationError as exc:
        fallback_voice = (payload.fallback_voice or "").strip()
        if fallback_voice and fallback_voice != voice:
            try:
                result = synthesize_speech(
                    settings,
                    provider=payload.voice_provider,
                    text=payload.text,
                    voice=fallback_voice,
                    model=payload.tts_model or payload.realtime_model,
                    instructions=instructions,
                    response_format=payload.preview_audio_format,
                    output_audio_format=payload.output_audio_format,
                    telephony_codec=payload.telephony_codec,
                    locale=payload.voice_locale,
                    gender=payload.voice_gender,
                    provider_region=payload.azure_speech_region,
                    voice_style=payload.voice_style,
                    voice_speed=payload.voice_speed,
                    voice_pitch=payload.voice_pitch,
                    voice_stability=payload.voice_stability,
                    voice_similarity=payload.voice_similarity,
                    voice_temperature=payload.voice_temperature,
                )
            except TTSGenerationError:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=str(exc),
                ) from exc
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
    return Response(
        content=result.audio,
        media_type=result.media_type,
    )


@router.get(
    "/clinics/{clinic_id}/assistant-configs",
    response_model=Page[AssistantConfigRead],
    tags=["Admin · Assistant configs"],
)
def list_assistant_configs(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> Page[AssistantConfigRead]:
    """List assistant prompt and voice configurations."""
    clinic_or_404(session, clinic_id)
    statement = select(AssistantConfig).where(AssistantConfig.clinic_id == clinic_id)
    if is_active is not None:
        statement = statement.where(AssistantConfig.is_active.is_(is_active))
    return paginate(
        session,
        statement.order_by(AssistantConfig.created_at.desc()),
        schema=AssistantConfigRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics/{clinic_id}/assistant-configs",
    response_model=AssistantConfigRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Assistant configs"],
)
def create_assistant_config(
    clinic_id: uuid.UUID,
    payload: AssistantConfigCreate,
    session: Annotated[Session, Depends(get_db)],
) -> AssistantConfig:
    """Create one versioned assistant configuration."""
    clinic_or_404(session, clinic_id)
    if payload.is_active:
        _ensure_active_config_available(session, clinic_id)
    _validate_conversation_flow(
        session,
        clinic_id,
        payload.conversation_flow_id,
    )
    values = _assistant_config_values_for_create(payload)
    config = AssistantConfig(clinic_id=clinic_id, **values)
    session.add(config)
    commit_or_conflict(
        session,
        detail="The clinic already has an active assistant configuration.",
    )
    session.refresh(config)
    return config


@router.get(
    "/clinics/{clinic_id}/assistant-configs/{config_id}",
    response_model=AssistantConfigRead,
    tags=["Admin · Assistant configs"],
)
def get_assistant_config(
    clinic_id: uuid.UUID,
    config_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> AssistantConfig:
    """Get one assistant configuration."""
    return nested_or_404(
        session,
        AssistantConfig,
        clinic_id=clinic_id,
        resource_id=config_id,
        label="Assistant configuration",
    )


@router.patch(
    "/clinics/{clinic_id}/assistant-configs/{config_id}",
    response_model=AssistantConfigRead,
    tags=["Admin · Assistant configs"],
)
def update_assistant_config(
    clinic_id: uuid.UUID,
    config_id: uuid.UUID,
    payload: AssistantConfigUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> AssistantConfig:
    """Partially update one assistant configuration."""
    config = get_assistant_config(clinic_id, config_id, session)
    if payload.is_active is True:
        _ensure_active_config_available(
            session,
            clinic_id,
            exclude_id=config.id,
        )
    if "conversation_flow_id" in payload.model_fields_set:
        _validate_conversation_flow(
            session,
            clinic_id,
            payload.conversation_flow_id,
        )
    values = _assistant_config_values_for_update(config, payload)
    set_values(config, values)
    commit_or_conflict(
        session,
        detail="The clinic already has an active assistant configuration.",
    )
    session.refresh(config)
    return config


@router.post(
    "/clinics/{clinic_id}/assistant-configs/{config_id}/activate",
    response_model=AssistantConfigRead,
    tags=["Admin · Assistant configs"],
)
def activate_assistant_config(
    clinic_id: uuid.UUID,
    config_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> AssistantConfig:
    """Atomically activate one config and deactivate its clinic siblings."""
    config = get_assistant_config(clinic_id, config_id, session)
    session.execute(
        update(AssistantConfig)
        .where(AssistantConfig.clinic_id == clinic_id)
        .values(is_active=False),
        execution_options={"synchronize_session": "fetch"},
    )
    config.is_active = True
    commit_or_conflict(
        session,
        detail="The assistant configuration could not be activated.",
    )
    session.refresh(config)
    return config


@router.post(
    "/clinics/{clinic_id}/assistant-configs/{config_id}/preview-prompt",
    response_model=PromptPreviewResponse,
    tags=["Admin · Assistant configs"],
)
def preview_assistant_prompt(
    clinic_id: uuid.UUID,
    config_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> PromptPreviewResponse:
    """Render a selected configuration with current tenant-scoped data."""
    config = get_assistant_config(clinic_id, config_id, session)
    context = build_clinic_context(
        session,
        clinic_id=clinic_id,
        assistant_config_id=config_id,
    )
    return PromptPreviewResponse(
        clinic_id=clinic_id,
        config_id=config_id,
        realtime_model=config.realtime_model,
        realtime_voice=config.realtime_voice,
        language=config.language,
        first_message=config.first_message,
        prompt=build_realtime_instructions(context),
    )


@router.delete(
    "/clinics/{clinic_id}/assistant-configs/{config_id}",
    response_model=DeleteResponse,
    tags=["Admin · Assistant configs"],
)
def delete_assistant_config(
    clinic_id: uuid.UUID,
    config_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one assistant configuration."""
    config = get_assistant_config(clinic_id, config_id, session)
    session.delete(config)
    commit_or_conflict(session)
    return DeleteResponse(id=config_id)
