import { z } from "zod";

export const assistantConfigFormSchema = z.object({
  name: z.string().trim().min(1, "El nombre es obligatorio").max(200),
  is_active: z.boolean(),
  realtime_model: z.string().trim().min(1, "El modelo es obligatorio"),
  realtime_voice: z.string().trim().min(1, "La voz es obligatoria"),
  language: z.string().trim().min(2, "El idioma es obligatorio").max(16),
  temperature: z
    .string()
    .trim()
    .refine(
      (value) =>
        value === "" ||
        (Number.isFinite(Number(value)) &&
          Number(value) >= 0 &&
          Number(value) <= 2),
      "La temperatura debe estar entre 0 y 2",
    ),
  first_message: z.string().trim().min(1, "El primer mensaje es obligatorio"),
  system_prompt: z
    .string()
    .trim()
    .min(1, "El prompt de sistema es obligatorio")
    .max(12000, "El prompt es demasiado largo"),
  safety_prompt: z.string().trim().min(1, "El prompt de seguridad es obligatorio"),
  booking_policy_prompt: z
    .string()
    .trim()
    .min(1, "La política de reservas es obligatoria"),
  cancellation_policy_prompt: z
    .string()
    .trim()
    .min(1, "La política de cancelación es obligatoria"),
  transfer_policy_prompt: z
    .string()
    .trim()
    .min(1, "La política de transferencia es obligatoria"),
  tone: z.enum(["profesional", "cercano", "comercial", "breve", "formal"]),
  response_length: z.enum(["corta", "normal", "detallada"]),
  ask_patient_name: z.boolean(),
  ask_patient_phone: z.boolean(),
  ask_general_reason: z.boolean(),
  allow_booking_without_worker: z.boolean(),
  allow_bookings: z.boolean(),
  allow_price_answers: z.boolean(),
  ask_service: z.boolean(),
  max_proposed_slots: z.number().int().min(1).max(10),
  max_consecutive_questions: z.number().int().min(1).max(5),
  conversation_style: z.enum(["natural", "formal", "comercial", "breve"]),
  initiative_level: z.enum(["bajo", "medio", "alto"]),
  commercial_call_handling: z.enum([
    "declinar",
    "transferir",
    "responder_basico",
  ]),
  allow_cancellations: z.boolean(),
  allow_reschedules: z.boolean(),
  natural_confirmation_required: z.boolean(),
  avoid_exact_confirmation_phrases: z.boolean(),
  additional_instructions: z.string(),
  forbidden_phrases: z.string(),
  no_availability_message: z.string(),
  missing_calendar_message: z.string(),
  emergency_message: z.string(),
  human_transfer_message: z.string(),
  human_transfer_rules: z.string(),
  commercial_call_message: z.string(),
  conversation_extra_rules: z.string(),
  closing_message: z.string(),
  use_prices: z.boolean(),
  use_knowledge_base: z.boolean(),
  strict_calendar_mode: z.boolean(),
  transcript_enabled: z.boolean(),
  recording_enabled: z.boolean(),
  conversation_retention_days: z.number().int().min(1).max(3650),
});

export type AssistantConfigFormValues = z.infer<
  typeof assistantConfigFormSchema
>;

export interface AssistantConfigPayload
  extends Omit<AssistantConfigFormValues, "temperature"> {
  temperature: string | null;
}

export const assistantConfigDefaults: AssistantConfigFormValues = {
  name: "Configuración principal",
  is_active: false,
  realtime_model: "gpt-realtime-2",
  realtime_voice: "marin",
  language: "es-ES",
  temperature: "",
  first_message:
    "Hola, soy el asistente virtual de la clínica. ¿En qué puedo ayudarle?",
  system_prompt:
    "Atiende de forma breve, amable y profesional. Gestiona información general y citas.",
  safety_prompt:
    "No diagnostiques ni recomiendes medicación. Ante una urgencia, indica llamar al 112 o acudir a urgencias.",
  booking_policy_prompt:
    "Recoge los datos mínimos, ofrece hasta tres huecos reales y reserva cuando el cliente acepte un hueco de forma natural.",
  cancellation_policy_prompt:
    "Identifica la cita correcta y confirma con la persona antes de cancelarla.",
  transfer_policy_prompt:
    "Transfiere a una persona cuando el usuario lo solicite o la petición quede fuera del alcance.",
  tone: "profesional",
  response_length: "normal",
  ask_patient_name: true,
  ask_patient_phone: true,
  ask_general_reason: true,
  allow_booking_without_worker: true,
  allow_bookings: true,
  allow_price_answers: true,
  ask_service: true,
  max_proposed_slots: 3,
  max_consecutive_questions: 2,
  conversation_style: "natural",
  initiative_level: "medio",
  commercial_call_handling: "declinar",
  allow_cancellations: true,
  allow_reschedules: true,
  natural_confirmation_required: true,
  avoid_exact_confirmation_phrases: true,
  additional_instructions: "",
  forbidden_phrases: "",
  no_availability_message:
    "No veo huecos en esa franja. Le propongo otras opciones cercanas.",
  missing_calendar_message:
    "Ahora mismo falta enlazar el calendario de ese profesional. Le puedo ofrecer otro profesional o avisar a recepción.",
  emergency_message:
    "Si es una urgencia médica, llame al 112 ahora o acuda a urgencias.",
  human_transfer_message:
    "Le paso con una persona del equipo si está disponible.",
  human_transfer_rules:
    "Transfiere si el usuario lo pide, si hay queja o si la peticiÃ³n queda fuera del alcance.",
  commercial_call_message:
    "Gracias, pero este nÃºmero es para pacientes y gestiÃ³n de citas. No atendemos llamadas comerciales por esta vÃ­a.",
  conversation_extra_rules:
    "No repitas preguntas ya respondidas. Usa los horarios propuestos para entender 'la primera', 'esa' o 'a las 9'.",
  closing_message: "Gracias por llamar. Hasta luego.",
  use_prices: true,
  use_knowledge_base: true,
  strict_calendar_mode: true,
  transcript_enabled: false,
  recording_enabled: false,
  conversation_retention_days: 30,
};

export const assistantTemplateNames = [
  "Clínica dental",
  "Peluquería",
  "Fisioterapia",
  "Psicología",
  "Medicina estética",
  "Clínica general",
] as const;

export type AssistantTemplateName = (typeof assistantTemplateNames)[number];

const templatePrompts: Record<
  AssistantTemplateName,
  Pick<
    AssistantConfigFormValues,
    | "first_message"
    | "system_prompt"
    | "safety_prompt"
    | "booking_policy_prompt"
    | "cancellation_policy_prompt"
    | "transfer_policy_prompt"
    | "tone"
    | "response_length"
    | "additional_instructions"
    | "forbidden_phrases"
    | "no_availability_message"
    | "missing_calendar_message"
    | "emergency_message"
    | "human_transfer_message"
    | "closing_message"
  >
> = {
  "Clínica dental": {
    first_message:
      "Hola, soy el asistente virtual de la clínica dental. ¿Desea pedir, cambiar o cancelar una cita?",
    system_prompt:
      "Informa sobre tratamientos dentales configurados, precios publicados, ubicación y citas. No valores síntomas ni diagnostiques.",
    safety_prompt:
      "No diagnostiques dolor dental ni recomiendes medicación. Si hay sangrado grave, dificultad respiratoria o urgencia, indica llamar al 112 o acudir a urgencias.",
    booking_policy_prompt:
      "Pregunta el motivo general, pero no solicites historia clínica. Ofrece solo servicios dentales reservables y huecos reales.",
    cancellation_policy_prompt:
      "Confirma nombre, teléfono y fecha aproximada antes de cancelar una cita dental.",
    transfer_policy_prompt:
      "Transfiere dudas clínicas, presupuestos complejos o peticiones fuera del catálogo.",
    tone: "profesional",
    response_length: "normal",
    additional_instructions: "Evita valorar dolor dental. Ofrece cita o transferencia.",
    forbidden_phrases: "Eso no es nada\nTome medicación",
    no_availability_message: "No veo huecos dentales en esa franja. Le doy alternativas.",
    missing_calendar_message:
      "Falta calendario del odontólogo. Le ofrezco otro profesional o aviso a recepción.",
    emergency_message:
      "Si hay sangrado grave, dificultad respiratoria o hinchazón rápida, llame al 112 o acuda a urgencias.",
    human_transfer_message: "Le paso con recepción para revisar el caso.",
    closing_message: "Gracias por llamar a la clínica dental. Hasta luego.",
  },
  Peluquería: {
    first_message:
      "Hola, soy el asistente virtual de la peluquería. ¿Qué servicio desea reservar?",
    system_prompt:
      "Gestiona información, precios y citas de peluquería con tono cercano y breve.",
    safety_prompt:
      "No hagas recomendaciones médicas sobre cuero cabelludo, alergias o lesiones.",
    booking_policy_prompt:
      "Confirma servicio, duración, profesional preferido y horario de forma natural antes de reservar.",
    cancellation_policy_prompt:
      "Identifica y confirma la cita antes de cancelarla.",
    transfer_policy_prompt:
      "Transfiere consultas técnicas complejas, quejas o presupuestos personalizados.",
    tone: "cercano",
    response_length: "corta",
    additional_instructions: "Usa un tono ágil, amable y comercial.",
    forbidden_phrases: "Te diagnostico\nGarantizado al 100%",
    no_availability_message: "Ese hueco no aparece libre. Te propongo otros horarios.",
    missing_calendar_message:
      "Falta enlazar agenda de ese profesional. Puedo mirar con otro compañero.",
    emergency_message:
      "Si esto es una urgencia médica, llama al 112 o acude a urgencias.",
    human_transfer_message: "Te paso con el equipo si está disponible.",
    closing_message: "Gracias por llamar. ¡Hasta luego!",
  },
  Fisioterapia: {
    first_message:
      "Hola, soy el asistente virtual del centro de fisioterapia. ¿En qué puedo ayudarle?",
    system_prompt:
      "Gestiona citas e información del centro. Recoge solo un motivo general y evita interpretar síntomas.",
    safety_prompt:
      "No diagnostiques lesiones ni recomiendes ejercicios o medicación. Ante síntomas graves o urgentes, indica 112 o urgencias.",
    booking_policy_prompt:
      "Ofrece solo sesiones reservables y confirma profesional, fecha y hora.",
    cancellation_policy_prompt:
      "Confirma la cita exacta antes de cancelar.",
    transfer_policy_prompt:
      "Transfiere preguntas clínicas, tratamientos personalizados o casos no configurados.",
    tone: "cercano",
    response_length: "normal",
    additional_instructions: "Recoge solo motivo general, sin pedir historia clínica.",
    forbidden_phrases: "Le diagnostico\nHaga estos ejercicios",
    no_availability_message: "No hay huecos en esa franja. Busco alternativas cercanas.",
    missing_calendar_message:
      "Falta calendario del fisioterapeuta. Recepción debe revisarlo.",
    emergency_message:
      "Si hay dolor fuerte, pérdida de fuerza súbita o situación urgente, llame al 112 o acuda a urgencias.",
    human_transfer_message: "Le paso con recepción para que le orienten.",
    closing_message: "Gracias por llamar al centro. Hasta luego.",
  },
  Psicología: {
    first_message:
      "Hola, soy el asistente virtual del centro. Puedo ayudarle con información y citas.",
    system_prompt:
      "Mantén un tono calmado, respetuoso y discreto. Gestiona únicamente información administrativa y citas.",
    safety_prompt:
      "No evalúes salud mental ni des terapia. Si existe riesgo inmediato para la persona o terceros, indica llamar al 112 o acudir a urgencias.",
    booking_policy_prompt:
      "Recoge solo un motivo general, sin pedir detalles sensibles, y reserva cuando acepte un hueco.",
    cancellation_policy_prompt:
      "Protege la privacidad y confirma la cita correcta antes de cancelarla.",
    transfer_policy_prompt:
      "Transfiere cualquier petición clínica, situación de crisis o solicitud de hablar con una persona.",
    tone: "formal",
    response_length: "normal",
    additional_instructions: "Mantén privacidad y evita pedir detalles sensibles.",
    forbidden_phrases: "No se preocupe por eso\nYo le doy terapia",
    no_availability_message: "No veo disponibilidad en esa franja. Le propongo alternativas.",
    missing_calendar_message:
      "Falta calendario del profesional. Puedo pedir que recepción lo revise.",
    emergency_message:
      "Si existe riesgo inmediato para usted o terceros, llame al 112 o acuda a urgencias.",
    human_transfer_message: "Puedo intentar pasarle con una persona del equipo.",
    closing_message: "Gracias por contactar. Hasta luego.",
  },
  "Medicina estética": {
    first_message:
      "Hola, soy el asistente virtual de la clínica de medicina estética. ¿Desea información o reservar una cita?",
    system_prompt:
      "Informa únicamente sobre servicios y precios configurados. No prometas resultados ni evalúes idoneidad clínica.",
    safety_prompt:
      "No diagnostiques, no recomiendes tratamientos ni medicación y no valores contraindicaciones.",
    booking_policy_prompt:
      "Reserva solo valoraciones o servicios marcados como reservables. No inventes precios ni resultados.",
    cancellation_policy_prompt:
      "Confirma identidad y cita antes de cancelar.",
    transfer_policy_prompt:
      "Transfiere consultas clínicas, contraindicaciones, resultados esperados o presupuestos personalizados.",
    tone: "comercial",
    response_length: "normal",
    additional_instructions: "No prometas resultados ni valores idoneidad clínica.",
    forbidden_phrases: "Resultado garantizado\nSin riesgos",
    no_availability_message: "No tengo huecos en esa franja. Le propongo opciones cercanas.",
    missing_calendar_message:
      "Falta calendario de ese profesional. Puedo mirar otro o avisar a recepción.",
    emergency_message:
      "Si es una urgencia médica, llame al 112 ahora o acuda a urgencias.",
    human_transfer_message: "Le paso con recepción para una valoración más personalizada.",
    closing_message: "Gracias por llamar a la clínica. Hasta luego.",
  },
  "Clínica general": {
    first_message:
      "Hola, soy el asistente virtual de la clínica. Puedo ayudarle con información y gestión de citas.",
    system_prompt:
      "Gestiona información administrativa, servicios y citas con respuestas breves y profesionales.",
    safety_prompt:
      "No diagnostiques ni recomiendes medicación. Ante una urgencia, dolor fuerte, dificultad respiratoria, pérdida de consciencia o sangrado grave, indica 112 o urgencias.",
    booking_policy_prompt:
      "Recoge datos mínimos, propone hasta tres huecos reales y reserva cuando acepte un hueco de forma natural.",
    cancellation_policy_prompt:
      "Identifica la cita y confirma antes de cancelarla.",
    transfer_policy_prompt:
      "Transfiere peticiones fuera de alcance, dudas clínicas o solicitud expresa.",
    tone: "profesional",
    response_length: "normal",
    additional_instructions: "Prioriza frases cortas y no pidas confirmaciones exactas.",
    forbidden_phrases: "Le diagnostico\nTome esta medicación",
    no_availability_message: "No tengo huecos en esa franja. Le propongo otras opciones.",
    missing_calendar_message:
      "Falta enlazar el calendario del trabajador. Recepción debe revisarlo.",
    emergency_message:
      "Ante urgencia, dolor fuerte, dificultad respiratoria, pérdida de consciencia o sangrado grave, llame al 112 o acuda a urgencias.",
    human_transfer_message: "Le paso con una persona si está disponible.",
    closing_message: "Gracias por llamar. Hasta luego.",
  },
};

export function applyAssistantTemplate(
  current: AssistantConfigFormValues,
  template: AssistantTemplateName,
): AssistantConfigFormValues {
  return {
    ...current,
    ...templatePrompts[template],
  };
}
