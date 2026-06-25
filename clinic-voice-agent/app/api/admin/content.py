"""CRUD endpoints for clinic knowledge and conversation flows."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin_schemas import (
    ConversationFlowCreate,
    ConversationFlowRead,
    ConversationFlowTemplateRead,
    ConversationFlowUpdate,
    DeleteResponse,
    KnowledgeItemCreate,
    KnowledgeItemRead,
    KnowledgeItemUpdate,
    Page,
    PromptContextKnowledgeRead,
    PromptContextPreviewResponse,
    PromptContextServiceRead,
    PromptContextWorkerRead,
    PromptPreviewResponse,
)
from app.api.admin.common import (
    apply_update,
    clinic_or_404,
    commit_or_conflict,
    nested_or_404,
    paginate,
)
from app.conversation_flows import list_flow_templates
from app.db import get_db
from app.models import (
    AssistantConfig,
    ConversationFlow,
    GoogleCredential,
    KnowledgeCategory,
    KnowledgeItem,
    PhoneNumber,
    Service,
    Worker,
)
from app.openai_realtime.prompt_builder import (
    build_clinic_context,
    build_realtime_instructions,
    render_service_price,
)

router = APIRouter(prefix="/admin")


@router.get(
    "/clinics/{clinic_id}/knowledge",
    response_model=Page[KnowledgeItemRead],
    tags=["Admin · Knowledge"],
)
def list_knowledge(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    category: Annotated[KnowledgeCategory | None, Query()] = None,
    q: str | None = Query(default=None, min_length=1, max_length=200),
) -> Page[KnowledgeItemRead]:
    """List ordered clinic knowledge used as LLM context."""
    clinic_or_404(session, clinic_id)
    statement = select(KnowledgeItem).where(KnowledgeItem.clinic_id == clinic_id)
    if is_active is not None:
        statement = statement.where(KnowledgeItem.is_active.is_(is_active))
    if category is not None:
        statement = statement.where(KnowledgeItem.category == category)
    if q is not None:
        search = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                KnowledgeItem.title.ilike(search),
                KnowledgeItem.content.ilike(search),
            )
        )
    return paginate(
        session,
        statement.order_by(
            KnowledgeItem.priority.desc(),
            KnowledgeItem.title,
        ),
        schema=KnowledgeItemRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics/{clinic_id}/knowledge",
    response_model=KnowledgeItemRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Knowledge"],
)
def create_knowledge(
    clinic_id: uuid.UUID,
    payload: KnowledgeItemCreate,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeItem:
    """Create one clinic knowledge item."""
    clinic_or_404(session, clinic_id)
    item = KnowledgeItem(clinic_id=clinic_id, **payload.model_dump())
    session.add(item)
    commit_or_conflict(session)
    session.refresh(item)
    return item


@router.get(
    "/clinics/{clinic_id}/knowledge/{item_id}",
    response_model=KnowledgeItemRead,
    tags=["Admin · Knowledge"],
)
def get_knowledge(
    clinic_id: uuid.UUID,
    item_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeItem:
    """Get one clinic knowledge item."""
    return nested_or_404(
        session,
        KnowledgeItem,
        clinic_id=clinic_id,
        resource_id=item_id,
        label="Knowledge item",
    )


@router.patch(
    "/clinics/{clinic_id}/knowledge/{item_id}",
    response_model=KnowledgeItemRead,
    tags=["Admin · Knowledge"],
)
def update_knowledge(
    clinic_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: KnowledgeItemUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeItem:
    """Partially update one clinic knowledge item."""
    item = get_knowledge(clinic_id, item_id, session)
    apply_update(item, payload)
    commit_or_conflict(session)
    session.refresh(item)
    return item


@router.delete(
    "/clinics/{clinic_id}/knowledge/{item_id}",
    response_model=DeleteResponse,
    tags=["Admin · Knowledge"],
)
def delete_knowledge(
    clinic_id: uuid.UUID,
    item_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one clinic knowledge item."""
    item = get_knowledge(clinic_id, item_id, session)
    session.delete(item)
    commit_or_conflict(session)
    return DeleteResponse(id=item_id)


@router.get(
    "/clinics/{clinic_id}/prompt-context-preview",
    response_model=PromptContextPreviewResponse,
    tags=["Admin · Knowledge"],
)
def preview_prompt_context(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> PromptContextPreviewResponse:
    """Preview only active public data that can enter the assistant prompt."""
    clinic_or_404(session, clinic_id)
    workers = list(
        session.scalars(
            select(Worker)
            .where(
                Worker.clinic_id == clinic_id,
                Worker.is_active.is_(True),
            )
            .order_by(Worker.name, Worker.id)
        )
    )
    services = list(
        session.scalars(
            select(Service)
            .where(
                Service.clinic_id == clinic_id,
                Service.is_active.is_(True),
            )
            .order_by(Service.public_name, Service.id)
        )
    )
    knowledge_items = list(
        session.scalars(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.clinic_id == clinic_id,
                KnowledgeItem.is_active.is_(True),
            )
            .order_by(
                KnowledgeItem.priority.desc(),
                KnowledgeItem.title,
                KnowledgeItem.id,
            )
        )
    )
    assistant_config_id = session.scalar(
        select(AssistantConfig.id).where(
            AssistantConfig.clinic_id == clinic_id,
            AssistantConfig.is_active.is_(True),
        )
    )
    workers_by_id = {str(worker.id): worker for worker in workers}
    warnings: list[str] = []
    if not services:
        warnings.append("No hay servicios activos.")
    if not any(service.is_bookable_by_bot for service in services):
        warnings.append("No hay servicios reservables.")
    if not knowledge_items:
        warnings.append("No hay contexto cargado para el asistente.")
    if assistant_config_id is None:
        warnings.append("No hay una configuración activa del asistente.")
    if (
        session.scalar(
            select(PhoneNumber.id).where(
                PhoneNumber.clinic_id == clinic_id,
                PhoneNumber.is_active.is_(True),
            )
        )
        is None
    ):
        warnings.append("No hay número configurado.")
    if (
        session.scalar(
            select(GoogleCredential.id).where(
                GoogleCredential.clinic_id == clinic_id
            )
        )
        is None
    ):
        warnings.append("No hay calendario conectado.")
    if not workers:
        warnings.append("No hay trabajadores activos.")

    service_rows: list[PromptContextServiceRead] = []
    for service in services:
        if service.duration_minutes <= 0:
            warnings.append(
                f"{service.public_name}: Este servicio no tiene duración."
            )
        if not service.price_text and service.price_amount is None:
            warnings.append(f"{service.public_name}: Este servicio no tiene precio.")
        worker_names = (
            [
                workers_by_id[worker_id].name
                for worker_id in service.allowed_worker_ids
                if worker_id in workers_by_id
            ]
            if service.allowed_worker_ids is not None
            else [worker.name for worker in workers]
        )
        service_rows.append(
            PromptContextServiceRead(
                id=service.id,
                public_name=service.public_name,
                description=service.description,
                price=render_service_price(service),
                duration_minutes=service.duration_minutes,
                total_duration_minutes=(
                    service.buffer_before_minutes
                    + service.duration_minutes
                    + service.buffer_after_minutes
                ),
                requires_worker=service.requires_worker,
                worker_names=worker_names if service.requires_worker else [],
                is_bookable_by_bot=service.is_bookable_by_bot,
            )
        )

    return PromptContextPreviewResponse(
        clinic_id=clinic_id,
        assistant_config_id=assistant_config_id,
        services=service_rows,
        workers=[
            PromptContextWorkerRead(
                id=worker.id,
                name=worker.name,
                role=worker.role,
                calendar_linked=worker.calendar_id is not None,
            )
            for worker in workers
        ],
        knowledge_items=[
            PromptContextKnowledgeRead(
                id=item.id,
                title=item.title,
                category=item.category,
                content=item.content,
                priority=item.priority,
            )
            for item in knowledge_items
        ],
        warnings=warnings,
    )


@router.get(
    "/clinics/{clinic_id}/flows",
    response_model=Page[ConversationFlowRead],
    tags=["Admin · Conversation flows"],
)
def list_flows(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> Page[ConversationFlowRead]:
    """List configurable conversation flows."""
    clinic_or_404(session, clinic_id)
    statement = select(ConversationFlow).where(ConversationFlow.clinic_id == clinic_id)
    if is_active is not None:
        statement = statement.where(ConversationFlow.is_active.is_(is_active))
    return paginate(
        session,
        statement.order_by(ConversationFlow.name, ConversationFlow.id),
        schema=ConversationFlowRead,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/clinics/{clinic_id}/flows",
    response_model=ConversationFlowRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin · Conversation flows"],
)
def create_flow(
    clinic_id: uuid.UUID,
    payload: ConversationFlowCreate,
    session: Annotated[Session, Depends(get_db)],
) -> ConversationFlow:
    """Create one configurable conversation flow."""
    clinic_or_404(session, clinic_id)
    flow = ConversationFlow(clinic_id=clinic_id, **payload.model_dump())
    session.add(flow)
    commit_or_conflict(session)
    session.refresh(flow)
    return flow


@router.get(
    "/clinics/{clinic_id}/flow-templates",
    response_model=list[ConversationFlowTemplateRead],
    tags=["Admin · Conversation flows"],
)
def get_flow_templates(
    clinic_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> list[ConversationFlowTemplateRead]:
    """Return built-in valid templates for the clinic flow editor."""
    clinic_or_404(session, clinic_id)
    return [
        ConversationFlowTemplateRead.model_validate(template)
        for template in list_flow_templates()
    ]


@router.get(
    "/clinics/{clinic_id}/flows/{flow_id}",
    response_model=ConversationFlowRead,
    tags=["Admin · Conversation flows"],
)
def get_flow(
    clinic_id: uuid.UUID,
    flow_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> ConversationFlow:
    """Get one conversation flow."""
    return nested_or_404(
        session,
        ConversationFlow,
        clinic_id=clinic_id,
        resource_id=flow_id,
        label="Conversation flow",
    )


@router.patch(
    "/clinics/{clinic_id}/flows/{flow_id}",
    response_model=ConversationFlowRead,
    tags=["Admin · Conversation flows"],
)
def update_flow(
    clinic_id: uuid.UUID,
    flow_id: uuid.UUID,
    payload: ConversationFlowUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> ConversationFlow:
    """Partially update one conversation flow."""
    flow = get_flow(clinic_id, flow_id, session)
    apply_update(flow, payload)
    commit_or_conflict(session)
    session.refresh(flow)
    return flow


@router.post(
    "/clinics/{clinic_id}/flows/{flow_id}/preview-prompt",
    response_model=PromptPreviewResponse,
    tags=["Admin · Conversation flows"],
)
def preview_flow_prompt(
    clinic_id: uuid.UUID,
    flow_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
    config_id: Annotated[uuid.UUID, Query()],
) -> PromptPreviewResponse:
    """Preview one flow with a selected assistant config without associating it."""
    flow = get_flow(clinic_id, flow_id, session)
    config = nested_or_404(
        session,
        AssistantConfig,
        clinic_id=clinic_id,
        resource_id=config_id,
        label="Assistant configuration",
    )
    context = replace(
        build_clinic_context(
            session,
            clinic_id=clinic_id,
            assistant_config_id=config_id,
        ),
        active_conversation_flow=flow,
    )
    return PromptPreviewResponse(
        clinic_id=clinic_id,
        config_id=config.id,
        realtime_model=config.realtime_model,
        realtime_voice=config.realtime_voice,
        language=config.language,
        first_message=config.first_message,
        prompt=build_realtime_instructions(context),
    )


@router.delete(
    "/clinics/{clinic_id}/flows/{flow_id}",
    response_model=DeleteResponse,
    tags=["Admin · Conversation flows"],
)
def delete_flow(
    clinic_id: uuid.UUID,
    flow_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> DeleteResponse:
    """Delete one conversation flow."""
    flow = get_flow(clinic_id, flow_id, session)
    session.delete(flow)
    commit_or_conflict(session)
    return DeleteResponse(id=flow_id)
