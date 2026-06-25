"""Safety and schema tests for the future Realtime voice agent."""

from __future__ import annotations

from app.config import Settings
from app.openai_realtime.session import build_session_config
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


def test_create_appointment_requires_prior_verbal_confirmation() -> None:
    """Both prompt and schema should prevent unconfirmed reservations."""
    settings = Settings(_env_file=None)
    prompt = build_receptionist_instructions(settings).casefold()
    create_tool = next(
        tool for tool in get_realtime_tools() if tool["name"] == "create_appointment"
    )

    assert "confirmación verbal" in prompt
    assert "solo después" in prompt
    assert "create_appointment devuelva éxito" in prompt
    assert "confirmed_by_caller" in create_tool["parameters"]["required"]
    confirmation = create_tool["parameters"]["properties"]["confirmed_by_caller"]
    assert confirmation["const"] is True


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
