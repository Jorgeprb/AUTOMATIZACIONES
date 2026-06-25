"""Deterministic local conversation simulator for the clinic agent."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar.fake_client import (
    FakeGoogleCalendarClient,
    InMemoryCalendarBackend,
    default_fake_calendar_backend,
)
from app.calendar.google_client import (
    GoogleCalendarClient,
    get_authorized_calendar_client,
)
from app.config import Settings
from app.models import (
    Appointment,
    AppointmentStatus,
    AssistantConfig,
    CallEvent,
    CallSession,
    CallStatus,
    Clinic,
    KnowledgeItem,
    Service,
    Worker,
)
from app.openai_realtime.prompt_builder import render_service_price
from app.openai_realtime.tools import (
    CalendarClientProvider,
    ToolExecutionContext,
    execute_realtime_tool,
)

SimulationMode = Literal["no-google", "google-real"]
SessionFactory = Callable[[], Session]

EMERGENCY_TERMS = (
    "urgencia",
    "dolor fuerte",
    "dolor intenso",
    "dificultad respiratoria",
    "dificultad para respirar",
    "no puedo respirar",
    "perdida de consciencia",
    "inconsciente",
    "sangrado grave",
    "sangra mucho",
    "dolor toracico",
)
AFFIRMATIVE_TERMS = (
    "si",
    "confirmo",
    "de acuerdo",
    "correcto",
    "adelante",
)
NEGATIVE_TERMS = ("no", "cancela eso", "mejor no")
APPOINTMENT_TERMS = ("cita", "reserv", "consulta", "hueco")
CANCELLATION_TERMS = ("cancelar", "cancela", "anular", "anula")


class SimulationTurnRequest(BaseModel):
    """One user message sent to the deterministic local simulator."""

    message: str = Field(min_length=1, max_length=4000)
    call_session_id: uuid.UUID | None = None
    clinic_id: uuid.UUID | None = None
    mode: SimulationMode = "no-google"
    now: AwareDatetime | None = None


class SimulationSlot(BaseModel):
    """One slot proposed by the simulator."""

    worker_id: uuid.UUID
    worker_name: str
    start_at: datetime
    end_at: datetime


class SimulationTurnResponse(BaseModel):
    """Structured result of one deterministic agent turn."""

    call_session_id: uuid.UUID
    reply: str
    action: str
    awaiting_confirmation: bool = False
    proposed_slots: list[SimulationSlot] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


def _normalize(value: str) -> str:
    """Lowercase text and remove accents for intent matching."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()


def _extract_phone(message: str) -> str | None:
    """Extract a phone number from free text."""
    match = re.search(r"\+?\d[\d\s().-]{7,}\d", message)
    if match is None:
        return None
    raw = match.group(0)
    digits = "".join(character for character in raw if character.isdigit())
    return f"+{digits}" if raw.strip().startswith("+") else digits


def _extract_name(message: str) -> str | None:
    """Extract a short patient name after common Spanish phrases."""
    match = re.search(
        r"(?:me llamo|soy|mi nombre es)\s+"
        r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ' -]{2,80})",
        message,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    candidate = re.split(
        r"\s+(?:y|con|para|mi|telefono|teléfono)\b",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return candidate.strip(" ,.-") or None


def _extract_date(message: str, *, today: date) -> date | None:
    """Extract an ISO or relative local date."""
    normalized = _normalize(message)
    if "pasado manana" in normalized:
        return today + timedelta(days=2)
    if "manana" in normalized:
        return today + timedelta(days=1)
    if re.search(r"\bhoy\b", normalized):
        return today
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _extract_time_window(message: str) -> str | None:
    """Extract the supported scheduler time-window vocabulary."""
    normalized = _normalize(message)
    explicit = re.search(
        r"\b([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d\b",
        normalized,
    )
    if explicit:
        return explicit.group(0)
    if "tarde" in normalized:
        return "afternoon"
    if "noche" in normalized or "ultima hora" in normalized:
        return "evening"
    if "por la manana" in normalized or "de la manana" in normalized:
        return "morning"
    return None


def _is_emergency(message: str) -> bool:
    """Detect the explicit emergency phrases covered by the safety prompt."""
    normalized = _normalize(message)
    return any(term in normalized for term in EMERGENCY_TERMS)


def _is_affirmative(message: str) -> bool:
    """Return true for a clear booking confirmation."""
    normalized = _normalize(message).strip(" .,!¿?¡")
    return any(
        normalized == term
        or normalized.startswith(f"{term} ")
        or f" {term} " in f" {normalized} "
        for term in AFFIRMATIVE_TERMS
    )


def _is_negative(message: str) -> bool:
    """Return true for a clear rejection."""
    normalized = _normalize(message).strip(" .,!¿?¡")
    return any(normalized.startswith(term) for term in NEGATIVE_TERMS)


def _selected_slot_index(message: str) -> int | None:
    """Read first, second, or third choice from natural text."""
    normalized = _normalize(message)
    choices = {
        0: ("primera", "primero", "opcion 1", "opción 1", "numero 1"),
        1: ("segunda", "segundo", "opcion 2", "opción 2", "numero 2"),
        2: ("tercera", "tercero", "opcion 3", "opción 3", "numero 3"),
    }
    stripped = normalized.strip()
    if stripped in {"1", "2", "3"}:
        return int(stripped) - 1
    for index, terms in choices.items():
        if any(term in normalized for term in terms):
            return index
    return None


class SimulationEngine:
    """Run local agent turns against real domain services."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        mode: SimulationMode = "no-google",
        fake_backend: InMemoryCalendarBackend | None = None,
        now: datetime | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.mode = mode
        self.fake_backend = fake_backend or default_fake_calendar_backend
        self.now = now

    def _clock(self, clinic: Clinic) -> datetime:
        """Return the current instant in the clinic timezone."""
        current = self.now or datetime.now(UTC)
        return current.astimezone(ZoneInfo(clinic.timezone))

    def calendar_provider(self) -> CalendarClientProvider:
        """Select the fake or authorized Google Calendar provider."""
        if self.mode == "google-real":
            return get_authorized_calendar_client

        def fake_provider(
            session: Session,
            settings: Settings,
            clinic_id: uuid.UUID,
        ) -> GoogleCalendarClient:
            del settings
            appointments = session.scalars(
                select(Appointment).where(
                    Appointment.clinic_id == clinic_id,
                )
            )
            for appointment in appointments:
                if appointment.status is AppointmentStatus.CANCELLED:
                    self.fake_backend.delete_event(
                        appointment.google_calendar_id,
                        appointment.google_event_id,
                    )
                    continue
                if appointment.status not in {
                    AppointmentStatus.PENDING,
                    AppointmentStatus.CONFIRMED,
                }:
                    continue
                self.fake_backend.insert_event(
                    appointment.google_calendar_id,
                    {
                        "id": appointment.google_event_id,
                        "summary": f"Cita - {appointment.patient_name}",
                        "start": {"dateTime": appointment.start_at.isoformat()},
                        "end": {"dateTime": appointment.end_at.isoformat()},
                    },
                )
            return FakeGoogleCalendarClient(self.fake_backend)  # type: ignore[return-value]

        return fake_provider

    def _resolve_clinic(
        self,
        session: Session,
        clinic_id: uuid.UUID | None,
    ) -> Clinic:
        """Resolve an explicit clinic or the configured demo clinic."""
        if clinic_id is not None:
            clinic = session.get(Clinic, clinic_id)
        else:
            clinic = session.scalar(
                select(Clinic).where(
                    Clinic.phone_number == self.settings.clinic_phone_number
                )
            )
            if clinic is None:
                clinics = list(session.scalars(select(Clinic).limit(2)))
                clinic = clinics[0] if len(clinics) == 1 else None
        if clinic is None:
            raise ValueError("Clínica no encontrada. Ejecuta el seed demo.")
        return clinic

    def _prepare_fake_calendars(self, session: Session, clinic: Clinic) -> None:
        """Give unlinked demo workers deterministic local-only calendars."""
        if self.mode != "no-google":
            return
        changed = False
        workers = session.scalars(select(Worker).where(Worker.clinic_id == clinic.id))
        for worker in workers:
            if worker.calendar_id is None:
                worker.calendar_id = f"sim-{worker.id}@calendar.local"
                changed = True
        if changed:
            session.commit()

    def create_call(
        self,
        *,
        clinic_id: uuid.UUID | None = None,
        assistant_config_id: uuid.UUID | None = None,
        caller_phone: str = "simulation",
    ) -> CallSession:
        """Create one fake active CallSession."""
        with self.session_factory() as session:
            clinic = self._resolve_clinic(session, clinic_id)
            assistant_config: AssistantConfig | None = None
            if assistant_config_id is not None:
                assistant_config = session.scalar(
                    select(AssistantConfig).where(
                        AssistantConfig.id == assistant_config_id,
                        AssistantConfig.clinic_id == clinic.id,
                    )
                )
                if assistant_config is None:
                    raise ValueError(
                        "La configuración del asistente no pertenece a la clínica."
                    )
            self._prepare_fake_calendars(session, clinic)
            call = CallSession(
                clinic_id=clinic.id,
                assistant_config_id=(
                    assistant_config.id if assistant_config is not None else None
                ),
                openai_call_id=f"simulation-{uuid.uuid4().hex}",
                provider_call_id="local-simulator",
                caller_phone=caller_phone[:32],
                called_number=clinic.phone_number,
                status=CallStatus.ACTIVE,
                conversation_state_json={
                    "simulation": True,
                    "simulation_mode": self.mode,
                    "clinic_id": str(clinic.id),
                    "phase": "idle",
                    "draft": {},
                    "proposed_slots": [],
                },
            )
            session.add(call)
            session.commit()
            return call

    def _load_call(
        self,
        session: Session,
        call_session_id: uuid.UUID,
    ) -> tuple[CallSession, Clinic]:
        """Load and validate one simulated call."""
        call = session.get(CallSession, call_session_id)
        if call is None:
            raise ValueError("Sesión simulada no encontrada.")
        if not call.conversation_state_json.get("simulation"):
            raise ValueError("La sesión no pertenece al simulador.")
        clinic_id = uuid.UUID(str(call.conversation_state_json["clinic_id"]))
        clinic = session.get(Clinic, clinic_id)
        if clinic is None:
            raise ValueError("Clínica de la simulación no encontrada.")
        self._prepare_fake_calendars(session, clinic)
        return call, clinic

    def _save_event(
        self,
        session: Session,
        call: CallSession,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Persist raw simulator input, output, and tool traces."""
        session.add(
            CallEvent(
                call_session_id=call.id,
                event_type=event_type,
                payload_json=payload,
            )
        )

    def _execute_tool(
        self,
        call: CallSession,
        clinic: Clinic,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the same dispatcher used by Realtime calls."""
        context = ToolExecutionContext(
            settings=self.settings,
            session_factory=self.session_factory,
            call_session_id=call.id,
            clinic_id=clinic.id,
            openai_call_id=call.openai_call_id,
            calendar_client_provider=self.calendar_provider(),
            now=self.now,
        )
        return execute_realtime_tool(name, arguments, context)

    def _worker_and_service_updates(
        self,
        session: Session,
        clinic: Clinic,
        message: str,
    ) -> dict[str, Any]:
        """Extract worker and service IDs using local database names."""
        normalized = _normalize(message)
        updates: dict[str, Any] = {}
        workers = session.scalars(
            select(Worker).where(
                Worker.clinic_id == clinic.id,
                Worker.is_active.is_(True),
            )
        )
        for worker in workers:
            if _normalize(worker.name) in normalized:
                updates["worker_id"] = str(worker.id)
                updates["worker_name"] = worker.name
                break
        services = list(
            session.scalars(
                select(Service)
                .where(
                    Service.clinic_id == clinic.id,
                    Service.is_active.is_(True),
                )
                .order_by(Service.name)
            )
        )
        for service in services:
            if (
                _normalize(service.name) in normalized
                or _normalize(service.public_name) in normalized
            ):
                updates["service_id"] = str(service.id)
                updates["service_name"] = service.public_name
                break
        if "service_id" not in updates and len(services) == 1:
            updates["service_id"] = str(services[0].id)
            updates["service_name"] = services[0].name
        return updates

    def _update_draft(
        self,
        session: Session,
        clinic: Clinic,
        draft: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        """Merge information found in one user message."""
        updated = dict(draft)
        patient_name = _extract_name(message)
        patient_phone = _extract_phone(message)
        preferred_date = _extract_date(
            message,
            today=self._clock(clinic).date(),
        )
        time_window = _extract_time_window(message)
        if patient_name:
            updated["patient_name"] = patient_name
        if patient_phone:
            updated["patient_phone"] = patient_phone
        if preferred_date:
            updated["preferred_date"] = preferred_date.isoformat()
        if time_window:
            updated["preferred_time_window"] = time_window
        updated.update(self._worker_and_service_updates(session, clinic, message))
        normalized = _normalize(message)
        if "me da igual con quien" in normalized or "cualquiera" in normalized:
            updated.pop("worker_id", None)
            updated.pop("worker_name", None)
        if "revision" in normalized:
            updated["reason"] = "Revisión general"
        elif "consulta" in normalized:
            updated["reason"] = "Consulta general"
        return updated

    def _information_reply(
        self,
        session: Session,
        call: CallSession,
        clinic: Clinic,
        message: str,
    ) -> tuple[str, list[dict[str, Any]]] | None:
        """Answer configured service, price, and knowledge questions."""
        normalized = _normalize(message)
        information_terms = (
            "cuanto",
            "precio",
            "cuesta",
            "informacion",
            "horario",
            "direccion",
            "donde",
            "seguro",
        )
        if not any(term in normalized for term in information_terms):
            return None

        tool_result = self._execute_tool(
            call,
            clinic,
            "get_clinic_info",
            {"clinic_id": str(clinic.id)},
        )
        trace = {
            "name": "get_clinic_info",
            "arguments": {"clinic_id": str(clinic.id)},
            "result": tool_result,
        }
        services = session.scalars(
            select(Service)
            .where(
                Service.clinic_id == clinic.id,
                Service.is_active.is_(True),
            )
            .order_by(Service.public_name)
        )
        for service in services:
            names = (_normalize(service.name), _normalize(service.public_name))
            if any(name and name in normalized for name in names):
                price = render_service_price(service)
                return (
                    f"{service.public_name}: {price}.",
                    [trace],
                )

        knowledge = session.scalars(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.clinic_id == clinic.id,
                KnowledgeItem.is_active.is_(True),
            )
            .order_by(KnowledgeItem.priority.desc())
        )
        message_words = {
            word for word in re.findall(r"[a-z0-9]+", normalized) if len(word) > 3
        }
        for item in knowledge:
            haystack = _normalize(f"{item.title} {item.content}")
            if any(word in haystack for word in message_words):
                return (item.content, [trace])
        if "direccion" in normalized or "donde" in normalized:
            return (
                clinic.address or "La dirección no está configurada.",
                [trace],
            )
        if "horario" in normalized:
            return (
                "Consulta el horario configurado de la clínica en recepción.",
                [trace],
            )
        return (
            "No tengo ese dato configurado. Puedes consultarlo con recepción.",
            [trace],
        )

    def _propose(
        self,
        call: CallSession,
        clinic: Clinic,
        draft: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Prefer the named worker, then same-day alternatives, then later days."""
        base_arguments: dict[str, Any] = {
            "clinic_id": str(clinic.id),
            "service_id": draft["service_id"],
            "preferred_date": draft["preferred_date"],
            "preferred_time_window": draft.get("preferred_time_window"),
            "max_slots": 3,
        }
        attempts: list[dict[str, Any]] = []
        worker_id = draft.get("worker_id")
        if worker_id:
            attempts.append(
                {
                    **base_arguments,
                    "worker_id": worker_id,
                    "days_ahead": 1,
                }
            )
            attempts.append({**base_arguments, "days_ahead": 1})
        attempts.append({**base_arguments, "days_ahead": 14})

        result: dict[str, Any] = {"ok": True, "slots": []}
        traces: list[dict[str, Any]] = []
        for arguments in attempts:
            result = self._execute_tool(call, clinic, "propose_slots", arguments)
            traces.append(
                {
                    "name": "propose_slots",
                    "arguments": arguments,
                    "result": result,
                }
            )
            if result.get("slots") or not result.get("ok"):
                break
        return result, traces

    def _slot_reply(self, slots: list[dict[str, Any]]) -> str:
        """Render up to three short telephone-style options."""
        parts = []
        for index, slot in enumerate(slots[:3], start=1):
            start_at = datetime.fromisoformat(str(slot["start_at"]))
            parts.append(
                f"{index}: {slot['worker_name']}, "
                f"{start_at.strftime('%d/%m a las %H:%M')}"
            )
        return "Tengo estas opciones. " + ". ".join(parts) + ". ¿Cuál eliges?"

    def _missing_data_reply(self, draft: dict[str, Any]) -> str | None:
        """Ask for the next critical field."""
        if not draft.get("patient_name"):
            return "Dime tu nombre, por favor."
        if not draft.get("patient_phone"):
            return "Dime un teléfono de contacto, por favor."
        if not draft.get("service_id"):
            return "¿Qué servicio necesitas?"
        if not draft.get("preferred_date"):
            return "¿Qué día prefieres?"
        return None

    def _turn_response(
        self,
        *,
        call: CallSession,
        reply: str,
        action: str,
        state: dict[str, Any],
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> SimulationTurnResponse:
        """Build a typed response from persisted state."""
        slots = [
            SimulationSlot.model_validate(slot)
            for slot in state.get("proposed_slots", [])
        ]
        return SimulationTurnResponse(
            call_session_id=call.id,
            reply=reply,
            action=action,
            awaiting_confirmation=state.get("phase") == "awaiting_confirmation",
            proposed_slots=slots,
            tool_calls=tool_calls or [],
        )

    def turn(
        self,
        message: str,
        *,
        call_session_id: uuid.UUID | None = None,
        clinic_id: uuid.UUID | None = None,
    ) -> SimulationTurnResponse:
        """Process one user turn without OpenAI or a telephone call."""
        if call_session_id is None:
            call_session_id = self.create_call(clinic_id=clinic_id).id

        with self.session_factory() as session:
            call, clinic = self._load_call(session, call_session_id)
            state = dict(call.conversation_state_json)
            draft = dict(state.get("draft", {}))
            self._save_event(
                session,
                call,
                event_type="simulation.user_turn",
                payload={"message": message, "mode": self.mode},
            )

            if _is_emergency(message):
                reply = (
                    "Esto puede ser una urgencia. Llame al 112 ahora "
                    "o acuda a urgencias."
                )
                state.update(
                    {
                        "phase": "emergency",
                        "proposed_slots": [],
                        "emergency_detected": True,
                    }
                )
                return self._finish_turn(
                    session,
                    call,
                    state,
                    reply=reply,
                    action="emergency",
                )

            normalized = _normalize(message)
            if state.get("phase") == "cancellation_data" or any(
                term in normalized for term in CANCELLATION_TERMS
            ):
                phone = _extract_phone(message) or draft.get("patient_phone")
                target_date = _extract_date(
                    message,
                    today=self._clock(clinic).date(),
                )
                if not phone or target_date is None:
                    reply = "Dime el teléfono y la fecha aproximada de la cita."
                    state["phase"] = "cancellation_data"
                    state["draft"] = self._update_draft(
                        session,
                        clinic,
                        draft,
                        message,
                    )
                    return self._finish_turn(
                        session,
                        call,
                        state,
                        reply=reply,
                        action="request_cancellation_data",
                    )
                arguments = {
                    "clinic_id": str(clinic.id),
                    "patient_phone": phone,
                    "approximate_date": target_date.isoformat(),
                }
                result = self._execute_tool(
                    call,
                    clinic,
                    "cancel_appointment",
                    arguments,
                )
                trace = {
                    "name": "cancel_appointment",
                    "arguments": arguments,
                    "result": result,
                }
                if result.get("ok"):
                    reply = "La cita está cancelada."
                    state["phase"] = "cancelled"
                    action = "appointment_cancelled"
                else:
                    reply = "No pude cancelar la cita. Revisa los datos."
                    action = "cancellation_failed"
                return self._finish_turn(
                    session,
                    call,
                    state,
                    reply=reply,
                    action=action,
                    tool_calls=[trace],
                )

            if state.get("phase") == "awaiting_confirmation":
                if _is_negative(message):
                    state.update(
                        {
                            "phase": "idle",
                            "selected_slot": None,
                            "proposed_slots": [],
                        }
                    )
                    return self._finish_turn(
                        session,
                        call,
                        state,
                        reply="No reservo nada. Podemos buscar otro horario.",
                        action="booking_rejected",
                    )
                if not _is_affirmative(message):
                    return self._finish_turn(
                        session,
                        call,
                        state,
                        reply="Necesito un sí claro antes de reservar.",
                        action="confirmation_required",
                    )
                selected = state.get("selected_slot")
                if not isinstance(selected, dict):
                    state["phase"] = "idle"
                    return self._finish_turn(
                        session,
                        call,
                        state,
                        reply="El horario elegido ya no está disponible.",
                        action="selection_missing",
                    )
                arguments = {
                    "clinic_id": str(clinic.id),
                    "worker_id": selected["worker_id"],
                    "service_id": draft.get("service_id"),
                    "patient_name": draft["patient_name"],
                    "patient_phone": draft["patient_phone"],
                    "reason": draft.get("reason"),
                    "start_at": selected["start_at"],
                    "end_at": selected["end_at"],
                    "confirmed_by_caller": True,
                }
                result = self._execute_tool(
                    call,
                    clinic,
                    "create_appointment",
                    arguments,
                )
                trace = {
                    "name": "create_appointment",
                    "arguments": arguments,
                    "result": result,
                }
                if result.get("ok"):
                    confirmed_start = datetime.fromisoformat(str(result["start_at"]))
                    reply = (
                        f"Cita confirmada con {result['worker_name']} "
                        f"el {confirmed_start.strftime('%d/%m a las %H:%M')}."
                    )
                    state["phase"] = "booked"
                    state["appointment_id"] = result["appointment_id"]
                    action = "appointment_created"
                else:
                    reply = "No pude reservar. Hay que buscar otro horario."
                    state["phase"] = "idle"
                    action = "booking_failed"
                return self._finish_turn(
                    session,
                    call,
                    state,
                    reply=reply,
                    action=action,
                    tool_calls=[trace],
                )

            proposed_slots = state.get("proposed_slots", [])
            selected_index = _selected_slot_index(message)
            if selected_index is not None and proposed_slots:
                if selected_index >= len(proposed_slots):
                    return self._finish_turn(
                        session,
                        call,
                        state,
                        reply="Esa opción no existe. Elige una de las propuestas.",
                        action="invalid_selection",
                    )
                selected = proposed_slots[selected_index]
                state["selected_slot"] = selected
                state["phase"] = "awaiting_confirmation"
                start_at = datetime.fromisoformat(str(selected["start_at"]))
                reply = (
                    f"Has elegido {selected['worker_name']} el "
                    f"{start_at.strftime('%d/%m a las %H:%M')}. "
                    "¿Confirmas la reserva?"
                )
                if _is_affirmative(message):
                    call.conversation_state_json = state
                    session.commit()
                    return self.turn(
                        "Sí, confirmo",
                        call_session_id=call.id,
                    )
                return self._finish_turn(
                    session,
                    call,
                    state,
                    reply=reply,
                    action="confirmation_requested",
                )

            draft = self._update_draft(
                session,
                clinic,
                draft,
                message,
            )
            state["draft"] = draft
            if state.get("phase") != "gathering":
                information = self._information_reply(
                    session,
                    call,
                    clinic,
                    message,
                )
                if information is not None:
                    reply, traces = information
                    return self._finish_turn(
                        session,
                        call,
                        state,
                        reply=reply,
                        action="general_info",
                        tool_calls=traces,
                    )
            is_appointment_request = state.get("phase") == "gathering" or any(
                term in normalized for term in APPOINTMENT_TERMS
            )
            if not is_appointment_request:
                return self._finish_turn(
                    session,
                    call,
                    state,
                    reply=(
                        "Soy el asistente virtual. Puedo gestionar citas, "
                        "cambios, cancelaciones e información general."
                    ),
                    action="general_info",
                )

            missing_reply = self._missing_data_reply(draft)
            if missing_reply:
                state["phase"] = "gathering"
                return self._finish_turn(
                    session,
                    call,
                    state,
                    reply=missing_reply,
                    action="request_data",
                )

            result, traces = self._propose(call, clinic, draft)
            slots = result.get("slots", []) if result.get("ok") else []
            state["proposed_slots"] = slots
            state["phase"] = "choosing_slot" if slots else "no_slots"
            reply = (
                self._slot_reply(slots)
                if slots
                else "No encuentro huecos. Prueba otra fecha."
            )
            return self._finish_turn(
                session,
                call,
                state,
                reply=reply,
                action="slots_proposed" if slots else "no_slots",
                tool_calls=traces,
            )

    def _finish_turn(
        self,
        session: Session,
        call: CallSession,
        state: dict[str, Any],
        *,
        reply: str,
        action: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> SimulationTurnResponse:
        """Persist state and the full simulated agent result."""
        call.conversation_state_json = state
        if tool_calls:
            for trace in tool_calls:
                self._save_event(
                    session,
                    call,
                    event_type="simulation.tool_call",
                    payload=trace,
                )
        self._save_event(
            session,
            call,
            event_type="simulation.agent_turn",
            payload={
                "reply": reply,
                "action": action,
                "awaiting_confirmation": (
                    state.get("phase") == "awaiting_confirmation"
                ),
            },
        )
        session.commit()
        return self._turn_response(
            call=call,
            reply=reply,
            action=action,
            state=state,
            tool_calls=tool_calls,
        )
