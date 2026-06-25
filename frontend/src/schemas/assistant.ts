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
  system_prompt: z.string().trim().min(1, "El prompt de sistema es obligatorio"),
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
    "Recoge los datos mínimos, ofrece hasta tres huecos reales y confirma verbalmente antes de reservar.",
  cancellation_policy_prompt:
    "Identifica la cita correcta y confirma con la persona antes de cancelarla.",
  transfer_policy_prompt:
    "Transfiere a una persona cuando el usuario lo solicite o la petición quede fuera del alcance.",
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
  },
  Peluquería: {
    first_message:
      "Hola, soy el asistente virtual de la peluquería. ¿Qué servicio desea reservar?",
    system_prompt:
      "Gestiona información, precios y citas de peluquería con tono cercano y breve.",
    safety_prompt:
      "No hagas recomendaciones médicas sobre cuero cabelludo, alergias o lesiones.",
    booking_policy_prompt:
      "Confirma servicio, duración, profesional preferido y horario antes de reservar.",
    cancellation_policy_prompt:
      "Identifica y confirma la cita antes de cancelarla.",
    transfer_policy_prompt:
      "Transfiere consultas técnicas complejas, quejas o presupuestos personalizados.",
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
  },
  Psicología: {
    first_message:
      "Hola, soy el asistente virtual del centro. Puedo ayudarle con información y citas.",
    system_prompt:
      "Mantén un tono calmado, respetuoso y discreto. Gestiona únicamente información administrativa y citas.",
    safety_prompt:
      "No evalúes salud mental ni des terapia. Si existe riesgo inmediato para la persona o terceros, indica llamar al 112 o acudir a urgencias.",
    booking_policy_prompt:
      "Recoge solo un motivo general, sin pedir detalles sensibles, y confirma antes de reservar.",
    cancellation_policy_prompt:
      "Protege la privacidad y confirma la cita correcta antes de cancelarla.",
    transfer_policy_prompt:
      "Transfiere cualquier petición clínica, situación de crisis o solicitud de hablar con una persona.",
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
  },
  "Clínica general": {
    first_message:
      "Hola, soy el asistente virtual de la clínica. Puedo ayudarle con información y gestión de citas.",
    system_prompt:
      "Gestiona información administrativa, servicios y citas con respuestas breves y profesionales.",
    safety_prompt:
      "No diagnostiques ni recomiendes medicación. Ante una urgencia, dolor fuerte, dificultad respiratoria, pérdida de consciencia o sangrado grave, indica 112 o urgencias.",
    booking_policy_prompt:
      "Recoge datos mínimos, propone hasta tres huecos reales y exige confirmación verbal antes de reservar.",
    cancellation_policy_prompt:
      "Identifica la cita y confirma antes de cancelarla.",
    transfer_policy_prompt:
      "Transfiere peticiones fuera de alcance, dudas clínicas o solicitud expresa.",
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
