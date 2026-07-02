"""Validation, templates, and prompt rendering for conversational flows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ConversationFlow

FlowStepType = Literal["message", "collect", "tool", "confirmation"]

ALLOWED_FLOW_FIELDS = frozenset(
    {
        "intent",
        "patient_name",
        "patient_phone",
        "service",
        "reason",
        "preferred_date",
        "preferred_time_window",
        "worker_preference",
        "appointment_id",
        "approximate_date",
    }
)
ALLOWED_FLOW_TOOLS = frozenset(
    {
        "get_clinic_info",
        "propose_slots",
        "check_availability",
        "create_appointment",
        "cancel_appointment",
        "transfer_to_human",
        "end_call",
    }
)


class FlowStep(BaseModel):
    """One declarative step that guides, but does not hard-code, the LLM."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    type: FlowStepType
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    field: str | None = None
    required: bool = False
    tool_name: str | None = None

    @model_validator(mode="after")
    def validate_type_fields(self) -> FlowStep:
        """Require only the properties meaningful for each step type."""
        if self.type == "message":
            if not self.text:
                raise ValueError("message steps require text")
            if self.field or self.tool_name:
                raise ValueError("message steps cannot define field or tool_name")
        elif self.type == "collect":
            if self.field not in ALLOWED_FLOW_FIELDS:
                raise ValueError(f"invalid collect field: {self.field}")
            if self.text or self.tool_name:
                raise ValueError("collect steps cannot define text or tool_name")
        elif self.type == "tool":
            if self.tool_name not in ALLOWED_FLOW_TOOLS:
                raise ValueError(f"invalid tool_name: {self.tool_name}")
            if self.text or self.field:
                raise ValueError("tool steps cannot define text or field")
        elif self.type == "confirmation":
            if self.text or self.field or self.tool_name:
                raise ValueError(
                    "confirmation steps cannot define text, field, or tool_name"
                )
        return self


class FlowDefinition(BaseModel):
    """Version-one maintainable JSON contract for one clinic flow."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    objectives: list[str] = Field(default_factory=list, max_length=10)
    exit_conditions: list[str] = Field(default_factory=list, max_length=10)
    steps: list[FlowStep] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> FlowDefinition:
        """Prevent ambiguous order references in prompt rendering."""
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("flow step ids must be unique")
        return self


def validate_flow_json(value: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one JSON flow for database storage."""
    return FlowDefinition.model_validate(value).model_dump(
        mode="json",
        exclude_defaults=True,
    )


FLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "standard_booking": {
        "key": "standard_booking",
        "name": "Reserva estándar",
        "description": "Recoge datos mínimos, propone huecos y confirma la reserva.",
        "flow_json": {
            "name": "Reserva estándar",
            "objectives": ["Ayudar a crear una cita confirmada con datos mínimos."],
            "exit_conditions": [
                "La cita se crea con éxito.",
                "La persona rechaza reservar o pide ayuda humana.",
            ],
            "steps": [
                {
                    "id": "greeting",
                    "type": "message",
                    "text": "Saluda e indica que eres asistente virtual.",
                },
                {
                    "id": "collect_intent",
                    "type": "collect",
                    "field": "intent",
                    "required": True,
                },
                {
                    "id": "collect_patient_name",
                    "type": "collect",
                    "field": "patient_name",
                    "required": True,
                },
                {
                    "id": "collect_patient_phone",
                    "type": "collect",
                    "field": "patient_phone",
                    "required": True,
                },
                {
                    "id": "collect_service",
                    "type": "collect",
                    "field": "service",
                    "required": True,
                },
                {
                    "id": "collect_preference",
                    "type": "collect",
                    "field": "preferred_date",
                    "required": True,
                },
                {
                    "id": "propose_slots",
                    "type": "tool",
                    "tool_name": "propose_slots",
                },
                {
                    "id": "confirm",
                    "type": "confirmation",
                    "required": True,
                },
                {
                    "id": "create_appointment",
                    "type": "tool",
                    "tool_name": "create_appointment",
                },
            ],
        },
    },
    "appointment_cancellation": {
        "key": "appointment_cancellation",
        "name": "Cancelación de cita",
        "description": "Identifica una cita y confirma antes de cancelarla.",
        "flow_json": {
            "name": "Cancelación de cita",
            "objectives": ["Cancelar la cita correcta con autorización explícita."],
            "exit_conditions": [
                "La cita queda cancelada.",
                "No puede identificarse y se deriva a recepción.",
            ],
            "steps": [
                {
                    "id": "collect_intent",
                    "type": "collect",
                    "field": "intent",
                    "required": True,
                },
                {
                    "id": "collect_phone",
                    "type": "collect",
                    "field": "patient_phone",
                    "required": True,
                },
                {
                    "id": "collect_date",
                    "type": "collect",
                    "field": "approximate_date",
                    "required": True,
                },
                {
                    "id": "confirm",
                    "type": "confirmation",
                    "required": True,
                },
                {
                    "id": "cancel",
                    "type": "tool",
                    "tool_name": "cancel_appointment",
                },
            ],
        },
    },
    "price_information": {
        "key": "price_information",
        "name": "Información de precios",
        "description": "Responde solo con servicios y precios configurados.",
        "flow_json": {
            "name": "Información de precios",
            "objectives": ["Informar sin inventar servicios ni precios."],
            "exit_conditions": [
                "La duda queda resuelta.",
                "El precio no está configurado y se recomienda recepción.",
            ],
            "steps": [
                {
                    "id": "collect_service",
                    "type": "collect",
                    "field": "service",
                    "required": True,
                },
                {
                    "id": "clinic_info",
                    "type": "tool",
                    "tool_name": "get_clinic_info",
                },
            ],
        },
    },
    "human_transfer": {
        "key": "human_transfer",
        "name": "Transferencia a humano",
        "description": "Recoge el motivo general y solicita transferencia.",
        "flow_json": {
            "name": "Transferencia a humano",
            "objectives": ["Derivar de forma breve y segura a recepción."],
            "exit_conditions": ["La transferencia queda solicitada."],
            "steps": [
                {
                    "id": "collect_reason",
                    "type": "collect",
                    "field": "reason",
                    "required": False,
                },
                {
                    "id": "transfer",
                    "type": "tool",
                    "tool_name": "transfer_to_human",
                },
            ],
        },
    },
    "medical_emergency": {
        "key": "medical_emergency",
        "name": "Urgencia médica",
        "description": "Prioriza el protocolo 112 y evita reservas rutinarias.",
        "flow_json": {
            "name": "Urgencia médica",
            "objectives": [
                "Indicar llamar al 112 o acudir a urgencias ante riesgo inmediato."
            ],
            "exit_conditions": [
                "La persona confirma que buscará asistencia urgente.",
                "Se solicita transferencia tras comunicar el protocolo.",
            ],
            "steps": [
                {
                    "id": "emergency_message",
                    "type": "message",
                    "text": (
                        "Indica llamar al 112 o acudir a urgencias. "
                        "No continúes una reserva rutinaria."
                    ),
                },
                {
                    "id": "transfer",
                    "type": "tool",
                    "tool_name": "transfer_to_human",
                },
            ],
        },
    },
}


def list_flow_templates() -> list[dict[str, Any]]:
    """Return defensive normalized copies of all built-in templates."""
    return [
        {
            **template,
            "flow_json": validate_flow_json(template["flow_json"]),
        }
        for template in FLOW_TEMPLATES.values()
    ]


def _step_summary(step: FlowStep) -> str:
    """Render one compact recommended action."""
    if step.type == "message":
        return f"mensaje: {step.text}"
    if step.type == "collect":
        requirement = "obligatorio" if step.required else "opcional"
        return f"recoger {step.field} ({requirement})"
    if step.type == "tool":
        return f"usar {step.tool_name}"
    return "aceptar confirmación natural del cliente"


def render_flow_prompt(flow: ConversationFlow) -> str:
    """Render one validated flow as soft guidance for the LLM prompt."""
    definition = FlowDefinition.model_validate(flow.flow_json)
    required_fields = [
        step.field
        for step in definition.steps
        if step.type == "collect" and step.required and step.field
    ]
    tools = list(
        dict.fromkeys(
            step.tool_name
            for step in definition.steps
            if step.type == "tool" and step.tool_name
        )
    )
    objectives = definition.objectives or [
        flow.description or f"Completar el flujo {definition.name}."
    ]
    exits = definition.exit_conditions or [
        "El objetivo queda completado.",
        "La persona desiste o pide hablar con recepción.",
    ]
    order = "\n".join(
        f"{index}. {_step_summary(step)}"
        for index, step in enumerate(definition.steps, start=1)
    )
    return f"""# Flujo conversacional activo: {definition.name}

Este flujo es una guía flexible. No conviertas la conversación en un formulario
rígido. Si la persona se desvía, responde brevemente y vuelve al objetivo cuando
resulte natural.

Objetivos:
{chr(10).join(f"- {objective}" for objective in objectives)}

Campos obligatorios:
{chr(10).join(f"- {field}" for field in required_fields) or "- Ninguno."}

Orden recomendado:
{order}

Herramientas permitidas por este flujo:
{chr(10).join(f"- {tool}" for tool in tools) or "- Ninguna."}

Condiciones de salida:
{chr(10).join(f"- {condition}" for condition in exits)}

Las reglas globales de seguridad, veracidad y aceptación natural siguen teniendo
prioridad. No uses una herramienta fuera de esta lista para cumplir el objetivo
del flujo, salvo transfer_to_human o end_call cuando sean necesarios por
seguridad, petición del usuario o cierre natural.
""".strip()
