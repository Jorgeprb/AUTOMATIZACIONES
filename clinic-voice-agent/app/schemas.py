"""Shared Pydantic request and response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models import AppointmentSource, AppointmentStatus, CallStatus
from app.utils.privacy import MAX_GENERAL_REASON_LENGTH, normalize_general_reason


class HealthResponse(BaseModel):
    """Health-check payload."""

    status: Literal["ok"]
    service: str
    environment: str


class ComponentStatus(BaseModel):
    """Implementation status for a backend component."""

    component: str
    status: Literal["ready"]


class GoogleOAuthCallbackResponse(BaseModel):
    """Result returned after connecting the clinic Google account."""

    status: Literal["connected"]
    clinic_id: uuid.UUID
    account_email: str


class GoogleOAuthDiagnosticIssueResponse(BaseModel):
    """Safe Google OAuth configuration issue visible in the admin panel."""

    variable: str
    severity: Literal["error", "warning"]
    message: str
    help: str


class GoogleOAuthDiagnosticResponse(BaseModel):
    """Google OAuth configuration and connection diagnostics."""

    clinic_id: uuid.UUID
    configured: bool
    can_start_oauth: bool
    connected: bool
    needs_reauthorization: bool
    account_email: str | None
    redirect_uri: str | None
    public_base_url: str | None
    frontend_base_url: str
    issues: list[GoogleOAuthDiagnosticIssueResponse]


class GoogleOAuthStartUrlResponse(BaseModel):
    """Admin-safe response containing the next Google OAuth URL."""

    clinic_id: uuid.UUID
    authorization_url: str


class CalendarStatusResponse(BaseModel):
    """Connection status for a clinic's single Google account."""

    clinic_id: uuid.UUID
    connected: bool
    needs_reauthorization: bool
    account_email: str | None
    workers_total: int
    workers_linked: int


class CalendarInfoResponse(BaseModel):
    """Writable Google Calendar visible to the connected account."""

    id: str
    summary: str
    primary: bool
    access_role: str | None
    color_id: str | None
    background_color: str | None
    foreground_color: str | None
    time_zone: str | None


class EventColorResponse(BaseModel):
    """Color available for Google Calendar events."""

    id: str
    background: str
    foreground: str


class CalendarListResponse(BaseModel):
    """Writable calendars and event colors for one clinic account."""

    calendars: list[CalendarInfoResponse]
    event_colors: list[EventColorResponse]


class WorkerCalendarCreateRequest(BaseModel):
    """Optional customization when creating a worker calendar."""

    summary: str | None = Field(default=None, min_length=1, max_length=200)
    color_id: str | None = Field(default=None, max_length=32)


class WorkerCalendarLinkRequest(BaseModel):
    """Existing Google Calendar selected for a worker."""

    calendar_id: str = Field(min_length=1, max_length=320)
    color_id: str | None = Field(default=None, max_length=32)


class WorkerCalendarResponse(BaseModel):
    """Worker calendar mapping after creation or linking."""

    worker_id: uuid.UUID
    calendar_id: str
    color_id: str | None
    calendar: CalendarInfoResponse


class WorkerFreeBusyTestRequest(BaseModel):
    """Time range used to verify one linked worker calendar."""

    time_min: AwareDatetime
    time_max: AwareDatetime

    @model_validator(mode="after")
    def validate_interval(self) -> WorkerFreeBusyTestRequest:
        """Require a positive timezone-aware test interval."""
        if self.time_max <= self.time_min:
            raise ValueError("time_max must be after time_min")
        return self


class FreeBusyPeriodResponse(BaseModel):
    """One busy interval returned by Google Calendar."""

    start_at: datetime
    end_at: datetime


class WorkerFreeBusyTestResponse(BaseModel):
    """FreeBusy diagnostic result for one worker calendar."""

    worker_id: uuid.UUID
    calendar_id: str
    time_min: datetime
    time_max: datetime
    busy_ranges: list[FreeBusyPeriodResponse]


class CallRead(BaseModel):
    """Public representation of a persisted call."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    openai_call_id: str
    provider_call_id: str | None
    caller_phone: str
    called_number: str
    status: CallStatus
    transcript_text: str | None
    summary_text: str | None
    started_at: datetime
    ended_at: datetime | None


class AppointmentCreate(BaseModel):
    """Data required to request an appointment."""

    patient_name: str = Field(min_length=1, max_length=200)
    patient_phone: str = Field(min_length=3, max_length=32)
    reason: str | None = Field(
        default=None,
        max_length=MAX_GENERAL_REASON_LENGTH,
    )
    start_at: datetime
    end_at: datetime

    @field_validator("reason")
    @classmethod
    def validate_general_reason(cls, value: str | None) -> str | None:
        """Keep only a short general appointment motive."""
        return normalize_general_reason(value)


class AppointmentRead(AppointmentCreate):
    """Public representation of an appointment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: AppointmentStatus
    source: AppointmentSource
    google_calendar_id: str
    google_event_id: str


class AgentAvailabilityRequest(BaseModel):
    """Exact slot to recheck for a worker."""

    clinic_id: uuid.UUID
    worker_id: uuid.UUID
    start_at: AwareDatetime
    end_at: AwareDatetime
    service_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> AgentAvailabilityRequest:
        """Require a positive appointment interval."""
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class AgentAvailabilityResponse(BaseModel):
    """Availability result suitable for a voice-agent tool."""

    available: bool
    clinic_id: uuid.UUID
    worker_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    reason: str | None = None


class AgentProposeSlotsRequest(BaseModel):
    """Search preferences for real appointment slots."""

    clinic_id: uuid.UUID
    service_id: uuid.UUID | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    worker_id: uuid.UUID | None = None
    preferred_date: date | None = None
    preferred_time_window: str | None = None
    days_ahead: int = Field(default=14, ge=1, le=90)
    max_slots: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_duration_source(self) -> AgentProposeSlotsRequest:
        """Require exactly one source of appointment duration."""
        if (self.service_id is None) == (self.duration_minutes is None):
            raise ValueError("Provide exactly one of service_id or duration_minutes")
        return self


class AgentSlotResponse(BaseModel):
    """One proposed worker appointment slot."""

    worker_id: uuid.UUID
    worker_name: str
    calendar_id: str
    start_at: datetime
    end_at: datetime
    blocked_start_at: datetime
    blocked_end_at: datetime


class AgentProposeSlotsResponse(BaseModel):
    """Ranked appointment options."""

    slots: list[AgentSlotResponse]


class AgentCreateAppointmentRequest(BaseModel):
    """Confirmed patient and slot data for creating an appointment."""

    clinic_id: uuid.UUID
    worker_id: uuid.UUID
    service_id: uuid.UUID | None = None
    patient_name: str = Field(min_length=1, max_length=200)
    patient_phone: str = Field(min_length=3, max_length=32)
    reason: str | None = Field(
        default=None,
        max_length=MAX_GENERAL_REASON_LENGTH,
    )
    start_at: AwareDatetime
    end_at: AwareDatetime
    call_session_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)

    @field_validator("reason")
    @classmethod
    def validate_general_reason(cls, value: str | None) -> str | None:
        """Reject detailed free-form clinical narratives."""
        return normalize_general_reason(value)

    @model_validator(mode="after")
    def validate_interval(self) -> AgentCreateAppointmentRequest:
        """Require a positive appointment interval."""
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class AgentAppointmentConfirmation(BaseModel):
    """Structured confirmation returned after persistence in both systems."""

    status: Literal["confirmed"]
    appointment_id: uuid.UUID
    clinic_id: uuid.UUID
    worker_id: uuid.UUID
    worker_name: str
    service_id: uuid.UUID | None
    patient_name: str
    patient_phone: str
    start_at: datetime
    end_at: datetime
    google_calendar_id: str
    google_event_id: str


class AgentCancelAppointmentRequest(BaseModel):
    """Appointment lookup by ID or patient phone and approximate date."""

    clinic_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    patient_phone: str | None = Field(default=None, min_length=3, max_length=32)
    approximate_date: date | None = None

    @model_validator(mode="after")
    def validate_lookup(self) -> AgentCancelAppointmentRequest:
        """Require either an ID or the complete fallback lookup."""
        by_id = self.appointment_id is not None
        by_phone_date = (
            self.patient_phone is not None and self.approximate_date is not None
        )
        if by_id == by_phone_date:
            raise ValueError(
                "Provide appointment_id or patient_phone + approximate_date"
            )
        return self


class AgentCancellationConfirmation(BaseModel):
    """Structured cancellation result."""

    status: Literal["cancelled", "already_cancelled"]
    appointment_id: uuid.UUID
    patient_name: str
    patient_phone: str
    start_at: datetime
    worker_id: uuid.UUID
    google_event_id: str


class AgentClinicInfoRequest(BaseModel):
    """Clinic identifier for administrative information."""

    clinic_id: uuid.UUID


class AgentWorkerInfo(BaseModel):
    """Worker details relevant to voice scheduling."""

    id: uuid.UUID
    name: str
    role: str
    is_active: bool
    calendar_linked: bool


class AgentServiceInfo(BaseModel):
    """Bookable service details."""

    id: uuid.UUID
    name: str
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int


class AgentClinicInfoResponse(BaseModel):
    """Clinic information exposed to the internal voice agent."""

    id: uuid.UUID
    name: str
    timezone: str
    phone_number: str
    workers: list[AgentWorkerInfo]
    services: list[AgentServiceInfo]


class CallDeleteResponse(BaseModel):
    """Confirmation after deleting a stored call session."""

    status: Literal["deleted"]
    call_session_id: uuid.UUID
