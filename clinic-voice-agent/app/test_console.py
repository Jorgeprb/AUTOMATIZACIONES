"""Persistent browser test sessions for the clinic assistant."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, cast

from openai import OpenAI, OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_schemas import (
    TestChatMessage,
    TestExtractedState,
    TestSessionRead,
    TestToolTrace,
)
from app.audio import TTSGenerationError, synthesize_openai_speech
from app.config import Settings
from app.conversation_policy import load_conversation_state
from app.models import (
    AssistantConfig,
    CallEvent,
    CallSession,
    CallStatus,
    Clinic,
    TestSession,
)
from app.openai_realtime.prompt_builder import (
    ClinicContext,
    build_clinic_context,
    build_realtime_instructions,
    render_service_price,
)
from app.openai_realtime.tools import (
    ToolExecutionContext,
    execute_realtime_tool,
    get_realtime_tools,
)
from app.simulation import (
    SimulationEngine,
    SimulationMode,
    _is_affirmative,
    _is_emergency,
)
from app.voice_profile import build_voice_instruction_block, effective_preview_voice

SessionFactory = Callable[[], Session]
TestEngine = Literal["simulator", "openai"]


class TestConsoleError(RuntimeError):
    """Stable error raised by the browser testing service."""


def _now_iso() -> str:
    """Return one JSON-safe UTC timestamp."""
    return datetime.now(UTC).isoformat()


def _message(
    role: Literal["user", "assistant"],
    content: str,
    *,
    action: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one persisted chat message."""
    return {
        "role": role,
        "content": content,
        "created_at": _now_iso(),
        "action": action,
        "tool_calls": tool_calls or [],
    }


def _call_id(test_session: TestSession) -> uuid.UUID:
    """Read the linked simulator CallSession identifier."""
    raw = test_session.state_json.get("call_session_id")
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise TestConsoleError(
            "La sesión no tiene una llamada simulada válida."
        ) from exc


def _test_engine(test_session: TestSession) -> TestEngine:
    """Read the persisted text engine."""
    value = str(test_session.state_json.get("engine", "simulator"))
    if value not in {"simulator", "openai"}:
        return "simulator"
    return cast(TestEngine, value)


def _calendar_mode(test_session: TestSession) -> SimulationMode:
    """Map the safety switch to the existing calendar providers."""
    return "google-real" if test_session.use_real_calendar else "no-google"


def _is_closed(test_session: TestSession) -> bool:
    """Return whether this browser test session has been closed."""
    return bool(test_session.state_json.get("closed"))


def _test_prompt(base_prompt: str, test_session: TestSession) -> str:
    """Append technical context that the real call dispatcher already knows."""
    return (
        f"{base_prompt}\n\n"
        "Contexto técnico de esta consola de prueba:\n"
        f"- clinic_id real: {test_session.clinic_id}\n"
        f"- call_session_id real: {_call_id(test_session)}\n"
        "Reglas técnicas: no inventes clinic_id ni call_session_id. Si una "
        "tool los necesita, puedes omitirlos; el servidor los inyecta desde "
        "esta sesión. Si ves IDs en una tool, no los corrijas ni los cambies. "
        "No inventes worker_id ni service_id: usa solo IDs reales del prompt o "
        "envía worker_name/service_name. No uses trabajadores sin calendar_id."
    )


def _tool_traces(messages: list[dict[str, Any]]) -> list[TestToolTrace]:
    """Collect tool traces from all assistant messages."""
    traces: list[TestToolTrace] = []
    for message in messages:
        for trace in message.get("tool_calls", []):
            try:
                traces.append(TestToolTrace.model_validate(trace))
            except ValueError:
                continue
    return traces


def _extracted_state(
    call: CallSession,
    traces: list[TestToolTrace],
) -> TestExtractedState:
    """Expose simulator state without leaking internal implementation details."""
    state = dict(call.conversation_state_json)
    conversation_state = load_conversation_state(state)
    draft = dict(state.get("draft", {}))
    appointment_id = conversation_state.appointment_id or state.get("appointment_id")
    if not appointment_id:
        for trace in reversed(traces):
            if trace.name == "create_appointment" and trace.result.get("ok"):
                appointment_id = trace.result.get("appointment_id")
                break
    service_name = draft.get("service_name")
    if not service_name and conversation_state.service:
        service_name = conversation_state.service.get("name")
    worker_name = draft.get("worker_name")
    if not worker_name and conversation_state.worker:
        worker_name = conversation_state.worker.get("name")
    return TestExtractedState(
        patient_name=conversation_state.patient_name or draft.get("patient_name"),
        patient_phone=conversation_state.patient_phone or draft.get("patient_phone"),
        service_name=service_name,
        worker_name=worker_name,
        preferred_date=conversation_state.preferred_date or draft.get("preferred_date"),
        preferred_time_window=(
            conversation_state.preferred_time_window
            or conversation_state.preferred_time
            or draft.get("preferred_time_window")
        ),
        phase=str(conversation_state.intent or state.get("phase", "idle")),
        appointment_confirmed=bool(appointment_id),
        appointment_id=appointment_id,
        emergency_detected=bool(state.get("emergency_detected")),
    )


def _audit_warnings(
    context: ClinicContext,
    messages: list[TestChatMessage],
    traces: list[TestToolTrace],
) -> list[str]:
    """Flag obvious claims that are not backed by current context or tools."""
    warnings: list[str] = []
    configured_prices = " ".join(
        render_service_price(service).casefold() for service in context.services
    )
    successful_booking = any(
        trace.name == "create_appointment" and trace.result.get("ok")
        for trace in traces
    )
    proposed_slots = any(
        trace.name == "propose_slots" and trace.result.get("ok")
        for trace in traces
    )
    if context.calendar_settings.workers_without_calendar:
        warnings.extend(
            f"El trabajador {worker_name} no tiene calendar_id y no se "
            "ofrecerá para reservas automáticas."
            for worker_name in context.calendar_settings.workers_without_calendar
        )
    if not context.workers:
        warnings.append(
            "No hay trabajadores activos; crea al menos uno antes de probar reservas."
        )
    elif not any(worker.calendar_id for worker in context.workers):
        warnings.append(
            "No hay trabajadores activos con calendar_id; asigna un calendario "
            "antes de probar reservas automáticas."
        )
    for message in messages:
        if message.role != "assistant":
            continue
        lowered = message.content.casefold()
        amounts = re.findall(r"\b\d+(?:[.,]\d{1,2})?\s*(?:€|euros?)", lowered)
        if amounts and any(amount not in configured_prices for amount in amounts):
            warnings.append(
                "La respuesta contiene un precio no encontrado en el contexto activo."
            )
        if "cita confirmada" in lowered and not successful_booking:
            warnings.append(
                "La respuesta afirma una reserva sin éxito de create_appointment."
            )
        if "tengo estas opciones" in lowered and not proposed_slots:
            warnings.append(
                "La respuesta ofrece horarios sin resultado de propose_slots."
            )
    return list(dict.fromkeys(warnings))


def render_test_session(
    session: Session,
    test_session: TestSession,
) -> TestSessionRead:
    """Build the complete browser response from persisted state."""
    context = build_clinic_context(
        session,
        clinic_id=test_session.clinic_id,
        assistant_config_id=test_session.assistant_config_id,
    )
    call = session.get(CallSession, _call_id(test_session))
    if call is None:
        raise TestConsoleError("La llamada simulada ya no existe.")
    messages = [
        TestChatMessage.model_validate(message)
        for message in test_session.messages_json
    ]
    traces = _tool_traces(test_session.messages_json)
    return TestSessionRead(
        id=test_session.id,
        clinic_id=test_session.clinic_id,
        assistant_config_id=test_session.assistant_config_id,
        assistant_config_name=context.active_assistant_config.name,
        use_real_calendar=test_session.use_real_calendar,
        engine=_test_engine(test_session),
        prompt=_test_prompt(build_realtime_instructions(context), test_session),
        messages=messages,
        state=_extracted_state(call, traces),
        tool_calls=traces,
        warnings=_audit_warnings(context, messages, traces),
        is_closed=_is_closed(test_session),
        created_at=test_session.created_at,
        updated_at=test_session.updated_at,
    )


def create_test_session(
    session: Session,
    session_factory: SessionFactory,
    settings: Settings,
    *,
    clinic_id: uuid.UUID,
    assistant_config_id: uuid.UUID,
    use_real_calendar: bool,
    engine: TestEngine | None,
) -> TestSession:
    """Create persistent test state and its linked fake CallSession."""
    clinic = session.get(Clinic, clinic_id)
    config = session.scalar(
        select(AssistantConfig).where(
            AssistantConfig.id == assistant_config_id,
            AssistantConfig.clinic_id == clinic_id,
        )
    )
    if clinic is None or config is None:
        raise TestConsoleError("Clínica o configuración no encontrada.")
    selected_engine = engine or settings.test_console_engine
    simulator = SimulationEngine(
        settings=settings,
        session_factory=session_factory,
        mode="google-real" if use_real_calendar else "no-google",
    )
    call = simulator.create_call(
        clinic_id=clinic_id,
        assistant_config_id=assistant_config_id,
        caller_phone="browser-test",
    )
    test_session = TestSession(
        clinic_id=clinic_id,
        assistant_config_id=assistant_config_id,
        use_real_calendar=use_real_calendar,
        messages_json=[
            _message(
                "assistant",
                config.first_message,
                action="initial_message",
            )
        ],
        state_json={
            "call_session_id": str(call.id),
            "engine": selected_engine,
        },
    )
    session.add(test_session)
    session.commit()
    session.refresh(test_session)
    return test_session


def _is_natural_booking_acceptance(content: str) -> bool:
    """Detect natural user acceptance of a proposed booking slot."""
    normalized = content.casefold()
    if _is_affirmative(content):
        return True
    if re.search(r"\b(?:a las\s*)?(?:[01]?\d|2[0-3])(?::[0-5]\d)?\b", normalized):
        return True
    natural_terms = (
        "me va bien",
        "resérvala",
        "reservala",
        "reserva",
        "quiero esa",
        "esa me va",
        "la primera",
        "la segunda",
        "la tercera",
        "opción 1",
        "opcion 1",
        "opción 2",
        "opcion 2",
        "opción 3",
        "opcion 3",
    )
    return any(term in normalized for term in natural_terms)


def _assistant_offered_slots(message: dict[str, Any]) -> bool:
    """Return whether an assistant message offered real scheduling options."""
    if message.get("role") != "assistant":
        return False
    for trace in message.get("tool_calls", []):
        if trace.get("name") == "propose_slots" and trace.get("result", {}).get("ok"):
            return True
    content = str(message.get("content", "")).casefold()
    return "opciones" in content or "hueco" in content


def _confirmation_allowed(messages: list[dict[str, Any]]) -> bool:
    """Allow create_appointment after natural acceptance of an offered slot."""
    slots_offered = False
    accepted_after_offer = False
    for message in messages:
        if _assistant_offered_slots(message):
            slots_offered = True
            accepted_after_offer = False
            continue
        if (
            slots_offered
            and message.get("role") == "user"
            and _is_natural_booking_acceptance(str(message.get("content", "")))
        ):
            accepted_after_offer = True
    return accepted_after_offer


def _run_openai_turn(
    test_session: TestSession,
    session_factory: SessionFactory,
    settings: Settings,
    prompt: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Run a bounded Responses API tool loop using the production dispatcher."""
    latest_message = str(test_session.messages_json[-1]["content"])
    if _is_emergency(latest_message):
        return (
            "Esto puede ser una urgencia. Llame al 112 ahora o acuda a urgencias.",
            "emergency",
            [],
        )
    call_id = _call_id(test_session)
    with session_factory() as session:
        call = session.get(CallSession, call_id)
        if call is None:
            raise TestConsoleError("La llamada simulada ya no existe.")
        clinic_id = test_session.clinic_id
        openai_call_id = call.openai_call_id
    simulator = SimulationEngine(
        settings=settings,
        session_factory=session_factory,
        mode=_calendar_mode(test_session),
    )
    context = ToolExecutionContext(
        settings=settings,
        session_factory=session_factory,
        call_session_id=call_id,
        clinic_id=clinic_id,
        openai_call_id=openai_call_id,
        calendar_client_provider=simulator.calendar_provider(),
    )
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    input_items: list[Any] = [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in test_session.messages_json
    ]
    traces: list[dict[str, Any]] = []
    for _ in range(6):
        responses_api = cast(Any, client.responses)
        try:
            response: Any = responses_api.create(
                model=settings.test_console_model,
                instructions=prompt,
                input=input_items,
                tools=list(get_realtime_tools()),
                tool_choice="auto",
            )
        except OpenAIError as exc:
            raise TestConsoleError(
                "OpenAI no pudo completar el turno de prueba."
            ) from exc
        output_items = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in response.output
        ]
        input_items.extend(output_items)
        function_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not function_calls:
            reply = str(response.output_text or "").strip()
            return reply or "No pude generar una respuesta.", "model_response", traces
        tool_outputs: list[dict[str, Any]] = []
        for item in function_calls:
            try:
                arguments = json.loads(item.arguments)
            except json.JSONDecodeError:
                arguments = {}
            if item.name == "create_appointment" and not _confirmation_allowed(
                test_session.messages_json
            ):
                result = {
                    "ok": False,
                    "error": (
                        "Falta aceptación natural previa del paciente para "
                        "ese hueco."
                    ),
                }
            else:
                result = execute_realtime_tool(item.name, arguments, context)
            traces.append(
                {
                    "name": item.name,
                    "arguments": arguments,
                    "result": result,
                }
            )
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
        input_items.extend(tool_outputs)
    raise TestConsoleError("El modelo superó el límite de llamadas a herramientas.")


def send_test_message(
    session: Session,
    session_factory: SessionFactory,
    settings: Settings,
    test_session: TestSession,
    message: str,
) -> TestSession:
    """Run one text turn through the configured engine and persist the trace."""
    if _is_closed(test_session):
        raise TestConsoleError("El chat de prueba ya está finalizado.")
    messages = list(test_session.messages_json)
    messages.append(_message("user", message))
    test_session.messages_json = messages
    session.commit()

    if _test_engine(test_session) == "openai":
        context = build_clinic_context(
            session,
            clinic_id=test_session.clinic_id,
            assistant_config_id=test_session.assistant_config_id,
        )
        reply, action, tool_calls = _run_openai_turn(
            test_session,
            session_factory,
            settings,
            _test_prompt(build_realtime_instructions(context), test_session),
        )
    else:
        simulator = SimulationEngine(
            settings=settings,
            session_factory=session_factory,
            mode=_calendar_mode(test_session),
        )
        result = simulator.turn(
            message,
            call_session_id=_call_id(test_session),
        )
        reply = result.reply
        action = result.action
        tool_calls = result.tool_calls

    messages = list(test_session.messages_json)
    messages.append(
        _message(
            "assistant",
            reply,
            action=action,
            tool_calls=tool_calls,
        )
    )
    test_session.messages_json = messages
    test_session.state_json = {
        **test_session.state_json,
        "last_action": action,
    }
    session.add(
        CallEvent(
            call_session_id=_call_id(test_session),
            event_type="test_console.turn",
            payload_json={
                "engine": _test_engine(test_session),
                "message": message,
                "reply": reply,
                "action": action,
                "tool_calls": tool_calls,
            },
        )
    )
    session.commit()
    session.refresh(test_session)
    return test_session


def close_test_session(
    session: Session,
    test_session: TestSession,
) -> TestSession:
    """Close one browser test session and its simulated call."""
    if _is_closed(test_session):
        return test_session
    call_id = _call_id(test_session)
    call = session.get(CallSession, call_id)
    if call is None:
        raise TestConsoleError("La llamada simulada ya no existe.")
    now = datetime.now(UTC)
    call.status = CallStatus.COMPLETED
    call.ended_at = now
    call.conversation_state_json = {
        **call.conversation_state_json,
        "test_console_closed": True,
    }
    test_session.state_json = {
        **test_session.state_json,
        "closed": True,
        "closed_at": now.isoformat(),
        "last_action": "closed",
    }
    session.add(
        CallEvent(
            call_session_id=call_id,
            event_type="test_console.closed",
            payload_json={
                "test_session_id": str(test_session.id),
                "engine": _test_engine(test_session),
            },
        )
    )
    session.commit()
    session.refresh(test_session)
    return test_session


def synthesize_test_session_audio(
    session: Session,
    settings: Settings,
    test_session: TestSession,
    text: str,
) -> bytes:
    """Generate one finite TTS audio blob using the selected AssistantConfig."""
    if _is_closed(test_session):
        raise TestConsoleError("El chat de prueba ya está finalizado.")
    cleaned = text.strip()
    if not cleaned:
        raise TestConsoleError("No hay texto para generar audio.")
    config = session.get(AssistantConfig, test_session.assistant_config_id)
    if config is None or config.clinic_id != test_session.clinic_id:
        raise TestConsoleError("Configuración del asistente no encontrada.")
    try:
        return synthesize_openai_speech(
            settings,
            text=cleaned,
            voice=effective_preview_voice(config),
            model=config.realtime_model,
            instructions=build_voice_instruction_block(config),
            response_format=config.preview_audio_format,
        )
    except TTSGenerationError as exc:
        raise TestConsoleError(str(exc)) from exc
