"""Safety and schema tests for the future Realtime voice agent."""

from __future__ import annotations

from app.config import Settings
from app.openai_realtime.session import RealtimeSessionConfig, build_session_config
from app.openai_realtime.tools import get_realtime_tools
from app.prompts import build_receptionist_instructions

EXPECTED_TOOL_NAMES = {
    "get_clinic_info",
    "propose_slots",
    "check_availability",
    "create_appointment",
    "cancel_appointment",
    "transfer_to_human",
    "end_call",
}


def test_all_realtime_tools_have_required_function_fields() -> None:
    """Every declared tool should have a useful OpenAI function schema."""
    tools = get_realtime_tools()

    assert {tool["name"] for tool in tools} == EXPECTED_TOOL_NAMES
    assert len(tools) == len(EXPECTED_TOOL_NAMES)
    for tool in tools:
        assert tool["type"] == "function"
        assert isinstance(tool["name"], str) and tool["name"]
        assert isinstance(tool["description"], str) and tool["description"]
        assert isinstance(tool["parameters"], dict)
        assert tool["parameters"]["type"] == "object"
        assert isinstance(tool["parameters"]["properties"], dict)
        assert "required" in tool["parameters"]
        assert tool["parameters"]["additionalProperties"] is False


def test_create_appointment_accepts_natural_slot_confirmation() -> None:
    """Prompt and schema should allow natural acceptance, not exact phrases."""
    settings = Settings(_env_file=None)
    prompt = build_receptionist_instructions(settings).casefold()
    create_tool = next(
        tool for tool in get_realtime_tools() if tool["name"] == "create_appointment"
    )

    assert "aceptación natural" in prompt
    assert "no pidas una" in prompt
    assert "frase exacta" in prompt
    assert "create_appointment devuelva éxito" in prompt
    assert "confirmed_by_caller" in create_tool["parameters"]["required"]
    confirmation = create_tool["parameters"]["properties"]["confirmed_by_caller"]
    assert confirmation["const"] is True
    assert "semánticamente" in confirmation["description"]


def test_propose_slots_schema_prefers_service_id_or_duration() -> None:
    """The model should see service_id and duration_minutes as alternatives."""
    propose_tool = next(
        tool for tool in get_realtime_tools() if tool["name"] == "propose_slots"
    )
    parameters = propose_tool["parameters"]
    properties = parameters["properties"]

    assert "oneOf" not in parameters
    assert {"service_id", "service_name", "duration_minutes"}.issubset(properties)
    assert parameters["type"] == "object"
    assert "service_id" in properties
    assert "service_name" in properties
    assert "duration_minutes" in properties
    assert "worker_name" in properties
    assert "no envíes duration_minutes" in properties["service_id"]["description"]
    assert "No envíes ambos campos" in properties["duration_minutes"]["description"]


def test_booking_tools_accept_names_for_server_resolution() -> None:
    """Realtime tools should allow names when the model does not know IDs."""
    tools = {tool["name"]: tool for tool in get_realtime_tools()}

    for name in ("check_availability", "create_appointment"):
        properties = tools[name]["parameters"]["properties"]
        assert "worker_name" in properties
        assert "service_name" in properties
    assert "worker_id" not in tools["check_availability"]["parameters"]["required"]
    assert "worker_id" not in tools["create_appointment"]["parameters"]["required"]


def test_prompt_tells_model_not_to_mix_service_and_duration() -> None:
    """The assistant prompt must steer tool calls away from duplicated duration."""
    settings = Settings(_env_file=None)
    prompt = build_receptionist_instructions(settings).casefold()

    assert "envía service_id" in prompt
    assert "no envíes" in prompt
    assert "duration_minutes" in prompt
    assert "nunca inventes uuid" in prompt
    assert "worker_name o service_name" in prompt


def test_prompt_contains_medical_prohibitions_and_emergency_protocol() -> None:
    """The receptionist must stay administrative and escalate emergencies."""
    settings = Settings(_env_file=None)
    prompt = build_receptionist_instructions(settings).casefold()

    assert "no diagnostiques" in prompt
    assert "no recomiendes" in prompt
    assert "medicación" in prompt
    assert "no realices" in prompt
    assert "triaje médico avanzado" in prompt
    assert "dolor fuerte" in prompt
    assert "dificultad respiratoria" in prompt
    assert "pérdida de consciencia" in prompt
    assert "sangrado grave" in prompt
    assert "llame al 112 ahora o acuda a urgencias" in prompt


def test_realtime_session_payload_exposes_declared_tools() -> None:
    """The future call-accept payload should include the tool declarations."""
    settings = Settings(_env_file=None)
    payload = build_session_config(settings).as_accept_payload()

    assert payload["tool_choice"] == "auto"
    assert {tool["name"] for tool in payload["tools"]} == EXPECTED_TOOL_NAMES


def test_realtime_session_payload_includes_voice_runtime_options() -> None:
    """Voice profile runtime switches should be sent only when configured."""
    config = RealtimeSessionConfig(
        model="gpt-realtime-2",
        voice="marin",
        instructions="Hola",
        transcription_enabled=False,
        allow_interruptions=False,
        idle_timeout_ms=5000,
    )

    payload = config.as_accept_payload()

    assert payload["audio"]["output"]["voice"] == "marin"
    assert payload["audio"]["input"]["turn_detection"]["idle_timeout_ms"] == 5000
    assert payload["audio"]["input"]["turn_detection"]["interrupt_response"] is False
