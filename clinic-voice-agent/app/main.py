"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    agent,
    calendar,
    calls,
    dev,
    google_auth,
    health,
    internal_voice,
    workers,
)
from app.config import Settings, get_settings
from app.openai_realtime import webhook
from app.openai_realtime.session import shutdown_call_control_tasks
from app.utils.logging import configure_logging
from app.utils.rate_limit import PublicRateLimitMiddleware
from app.utils.security import require_admin_api_key, require_internal_api_key

OPENAPI_TAGS = [
    {"name": "health", "description": "Process and PostgreSQL health checks."},
    {"name": "Admin · Clinics", "description": "Multi-clinic tenant management."},
    {
        "name": "Admin · Phone numbers",
        "description": "VoIP and telephone-number routing configuration.",
    },
    {"name": "Admin · Workers", "description": "Clinic worker management."},
    {
        "name": "Admin · Services and prices",
        "description": "Bookable services, prices, and worker restrictions.",
    },
    {
        "name": "Admin · Assistant configs",
        "description": "Realtime model, voice, and prompt versions.",
    },
    {
        "name": "Admin · Knowledge",
        "description": "Clinic facts supplied as LLM context.",
    },
    {
        "name": "Admin · Conversation flows",
        "description": "Structured assistant conversation flows.",
    },
    {
        "name": "Admin · Calls and conversations",
        "description": "Calls, transcripts, summaries, and raw events.",
    },
    {
        "name": "Admin · Appointments",
        "description": "Appointment administration and filtering.",
    },
    {
        "name": "Admin · Test console",
        "description": "Persistent text simulations using clinic prompts and tools.",
    },
    {
        "name": "Admin · Dashboard",
        "description": "Clinic readiness checklist and operational metrics.",
    },
    {
        "name": "Admin · Google Calendar",
        "description": "Google OAuth diagnostics and worker calendar linking.",
    },
    {"name": "google-auth", "description": "Google OAuth connection."},
    {"name": "calendar", "description": "Internal Google Calendar operations."},
    {"name": "workers", "description": "Internal worker calendar operations."},
    {"name": "agent-tools", "description": "Internal voice-agent tools."},
    {"name": "calls", "description": "Internal call maintenance."},
    {"name": "development", "description": "Local-only simulation routes."},
    {"name": "openai-realtime", "description": "OpenAI Realtime SIP webhook."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    application_settings = settings or get_settings()
    configure_logging(application_settings.log_level)
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_started",
            extra={"environment": application_settings.app_environment},
        )
        try:
            yield
        finally:
            await shutdown_call_control_tasks()
            logger.info("application_stopped")

    application = FastAPI(
        title="Clinic Voice Agent",
        version="0.1.0",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        docs_url=None
        if application_settings.app_environment == "production"
        else "/docs",
        redoc_url=None
        if application_settings.app_environment == "production"
        else "/redoc",
        openapi_url=(
            None
            if application_settings.app_environment == "production"
            else "/openapi.json"
        ),
    )
    application.state.settings = application_settings
    application.dependency_overrides[get_settings] = lambda: application_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=application_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Admin-API-Key",
            "X-Internal-API-Key",
            "X-Request-ID",
        ],
    )
    application.add_middleware(
        PublicRateLimitMiddleware,
        settings=application_settings,
    )

    @application.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    application.include_router(health.router)
    application.include_router(google_auth.router)
    internal_dependencies = [Depends(require_internal_api_key)]
    application.include_router(
        calendar.router,
        prefix="/api",
        dependencies=internal_dependencies,
    )
    application.include_router(
        workers.router,
        prefix="/api",
        dependencies=internal_dependencies,
    )
    application.include_router(
        agent.router,
        prefix="/api",
        dependencies=internal_dependencies,
    )
    application.include_router(
        calls.router,
        prefix="/api",
        dependencies=internal_dependencies,
    )
    application.include_router(
        internal_voice.router,
        prefix="/api",
        dependencies=internal_dependencies,
    )
    application.include_router(
        admin.router,
        prefix="/api",
        dependencies=[Depends(require_admin_api_key)],
    )
    if application_settings.app_environment != "production":
        application.include_router(dev.router)
    application.include_router(webhook.router)
    return application


app = create_app()
