import { z } from "zod";

export const callAudioModes = ["openai_hosted_sip", "vps_media_bridge"] as const;
export const voiceProviders = [
  "openai",
  "azure",
  "google",
  "elevenlabs",
  "amazon_polly",
  "deepgram",
  "cartesia",
  "resemble",
  "readspeaker",
  "acapela",
  "cereproc",
  "local_coqui",
  "local_chatterbox",
  "custom_http",
] as const;
export const telephonyCodecs = ["pcmu", "pcma", "pcm16"] as const;
export const outputAudioFormats = ["pcm16", "wav", "mp3", "opus"] as const;
export const clonedOrCustomVoiceProviders = [
  "elevenlabs",
  "resemble",
  "local_coqui",
  "local_chatterbox",
  "custom_http",
] as const;

const clonedOrCustomProviderSet = new Set<string>(clonedOrCustomVoiceProviders);

function requiredDecimalString(
  label: string,
  min: number,
  max: number,
) {
  return z
    .string()
    .trim()
    .refine(
      (value) =>
        value !== "" &&
        Number.isFinite(Number(value)) &&
        Number(value) >= min &&
        Number(value) <= max,
      `${label} debe estar entre ${min} y ${max}`,
    );
}

function optionalDecimalString(
  label: string,
  min: number,
  max: number,
) {
  return z
    .string()
    .trim()
    .refine(
      (value) =>
        value === "" ||
        (Number.isFinite(Number(value)) &&
          Number(value) >= min &&
          Number(value) <= max),
      `${label} debe estar entre ${min} y ${max}`,
    );
}

export const assistantConfigFormSchema = z
  .object({
  name: z.string().trim().min(1, "El nombre es obligatorio").max(200),
  is_active: z.boolean(),
  realtime_model: z.string().trim().min(1, "El modelo es obligatorio"),
  realtime_voice: z.string().trim().min(1, "La voz es obligatoria"),
  call_audio_mode: z.enum(callAudioModes),
  voice_provider: z.string().trim().min(1, "El proveedor de voz es obligatorio"),
  tts_model: z.string(),
  voice_id: z.string(),
  voice_locale: z.string(),
  voice_gender: z.string(),
  azure_speech_region: z.string(),
  voice_style: z.string(),
  voice_speed: requiredDecimalString("La velocidad de voz", 0.5, 2),
  voice_pitch: requiredDecimalString("El pitch", -24, 24),
  voice_stability: optionalDecimalString("La estabilidad", 0, 1),
  voice_similarity: optionalDecimalString("La similitud", 0, 1),
  voice_temperature: optionalDecimalString("La temperatura de voz", 0, 2),
  output_audio_format: z.enum(outputAudioFormats),
  telephony_codec: z.enum(telephonyCodecs),
  external_voice_legal_confirmed: z.boolean(),
  voice_instructions: z.string(),
  voice_preset: z.string(),
  tts_preview_voice: z.string(),
  fallback_voice: z.string(),
  speech_speed: z.enum(["slow", "normal", "fast"]),
  pause_style: z.enum(["short", "natural", "slow"]),
  phone_reading_style: z.enum(["digits", "groups", "natural"]),
  date_reading_style: z.enum(["natural", "numeric"]),
  price_reading_style: z.enum(["brief", "clear", "detailed"]),
  allow_interruptions: z.boolean(),
  turn_end_silence_ms: z
    .string()
    .trim()
    .refine(
      (value) =>
        Number.isInteger(Number(value)) &&
        Number(value) >= 200 &&
        Number(value) <= 1200,
      "El tiempo de fin de turno debe estar entre 200 y 1200 ms",
    ),
  idle_timeout_ms: z
    .string()
    .trim()
    .refine(
      (value) =>
        value === "" ||
        (Number.isInteger(Number(value)) &&
          Number(value) >= 1000 &&
          Number(value) <= 60000),
      "El timeout debe estar entre 1000 y 60000 ms",
    ),
  ai_disclosure_enabled: z.boolean(),
  ai_disclosure_message: z.string(),
  preview_audio_format: z.enum(["mp3", "wav", "opus"]),
  language: z.string().trim().min(2, "El idioma es obligatorio").max(16),
  temperature: z
    .string()
    .trim()
    .refine(
      (value) =>
        value === "" ||
        (Number.isFinite(Number(value)) &&
          Number(value) >= 0.6 &&
          Number(value) <= 1.2),
      "La temperatura debe estar entre 0.6 y 1.2",
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
  service_prompt_mode: z.enum([
    "list_services",
    "ask_open",
    "infer_confirm",
  ]),
  known_customer_name_enabled: z.boolean(),
  known_customer_greeting_enabled: z.boolean(),
  known_customer_greeting_template: z.string().max(1000),
  known_customer_explanation_template: z.string().max(2000),
  remember_customer_after_booking: z.boolean(),
  suggest_preferred_worker_enabled: z.boolean(),
  ask_worker_preference_enabled: z.boolean(),
  slot_interval_minutes: z.union([
    z.literal(5),
    z.literal(10),
    z.literal(15),
    z.literal(20),
    z.literal(30),
    z.literal(60),
  ]),
  direct_availability_response: z.boolean(),
  direct_booking_response: z.boolean(),
  booking_confirmation_datetime_enabled: z.boolean(),
  post_booking_followup_enabled: z.boolean(),
  post_booking_followup_message: z.string().max(300),
  hangup_after_no_more_help: z.boolean(),
  hangup_on_natural_goodbye: z.boolean(),
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
})
  .superRefine((value, ctx) => {
    if (
      value.voice_provider !== "openai" &&
      value.call_audio_mode !== "vps_media_bridge"
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["call_audio_mode"],
        message: "Las voces externas requieren VPS Media Bridge.",
      });
    }
    if (
      clonedOrCustomProviderSet.has(value.voice_provider) &&
      !value.external_voice_legal_confirmed
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["external_voice_legal_confirmed"],
        message:
          "Confirma derechos legales para usar voces clonadas o personalizadas.",
      });
    }
  });

export type AssistantConfigFormValues = z.infer<
  typeof assistantConfigFormSchema
>;

export interface AssistantConfigPayload
  extends Omit<
    AssistantConfigFormValues,
    | "temperature"
    | "idle_timeout_ms"
    | "turn_end_silence_ms"
    | "tts_model"
    | "voice_id"
    | "voice_locale"
    | "voice_gender"
    | "azure_speech_region"
    | "voice_style"
    | "voice_stability"
    | "voice_similarity"
    | "voice_temperature"
  > {
  temperature: string | null;
  idle_timeout_ms: number | null;
  turn_end_silence_ms: number;
  tts_model: string | null;
  voice_id: string | null;
  voice_locale: string | null;
  voice_gender: string | null;
  azure_speech_region: string | null;
  voice_style: string | null;
  voice_stability: string | null;
  voice_similarity: string | null;
  voice_temperature: string | null;
}

export const assistantConfigDefaults: AssistantConfigFormValues = {
  name: "Configuración principal",
  is_active: false,
  realtime_model: "gpt-realtime-2",
  realtime_voice: "marin",
  call_audio_mode: "openai_hosted_sip",
  voice_provider: "openai",
  tts_model: "",
  voice_id: "",
  voice_locale: "es-ES",
  voice_gender: "",
  azure_speech_region: "",
  voice_style: "",
  voice_speed: "1.00",
  voice_pitch: "0",
  voice_stability: "",
  voice_similarity: "",
  voice_temperature: "",
  output_audio_format: "pcm16",
  telephony_codec: "pcmu",
  external_voice_legal_confirmed: false,
  voice_instructions:
    "Habla con voz clara, amable y tranquila. Sonríe al hablar, evita sonar robótico y marca bien nombres, horas y teléfonos.",
  voice_preset: "Recepcionista clínica formal",
  tts_preview_voice: "",
  fallback_voice: "",
  speech_speed: "normal",
  pause_style: "natural",
  phone_reading_style: "groups",
  date_reading_style: "natural",
  price_reading_style: "clear",
  allow_interruptions: true,
  turn_end_silence_ms: "350",
  idle_timeout_ms: "",
  ai_disclosure_enabled: true,
  ai_disclosure_message: "Soy un asistente virtual de la clínica.",
  preview_audio_format: "mp3",
  language: "es-ES",
  temperature: "0.80",
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
  service_prompt_mode: "ask_open",
  known_customer_name_enabled: true,
  known_customer_greeting_enabled: true,
  known_customer_greeting_template: "Ola, {customer_name}. En que podo axudarche?",
  known_customer_explanation_template: "Non te preocupes, non son vidente. Recoñecín o número porque estás na base de datos para ofrecerche unha atención máis personalizada.",
  remember_customer_after_booking: true,
  suggest_preferred_worker_enabled: true,
  ask_worker_preference_enabled: true,
  slot_interval_minutes: 15,
  direct_availability_response: true,
  direct_booking_response: true,
  booking_confirmation_datetime_enabled: true,
  post_booking_followup_enabled: true,
  post_booking_followup_message: "¿Puedo ayudarte con algo más?",
  hangup_after_no_more_help: true,
  hangup_on_natural_goodbye: true,
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
    "Transfiere si el usuario lo pide, si hay queja o si la petición queda fuera del alcance.",
  commercial_call_message:
    "Gracias, pero este número es para pacientes y gestión de citas. No atendemos llamadas comerciales por esta vía.",
  conversation_extra_rules:
    "No repitas preguntas ya respondidas. Usa los horarios propuestos para entender 'la primera', 'esa' o 'a las 9'.",
  closing_message: "Gracias por llamar. Hasta luego.",
  use_prices: true,
  use_knowledge_base: true,
  strict_calendar_mode: true,
  transcript_enabled: true,
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

export const voicePresetNames = [
  "Recepcionista clínica formal",
  "Recepcionista cercana",
  "Peluquería/estética",
  "Clínica dental",
  "Fisioterapia",
  "Psicología",
  "Centralita breve",
  "Comercial suave",
] as const;

export type VoicePresetName = (typeof voicePresetNames)[number];

const voicePresets: Record<
  VoicePresetName,
  Pick<
    AssistantConfigFormValues,
    | "voice_instructions"
    | "voice_preset"
    | "speech_speed"
    | "pause_style"
    | "phone_reading_style"
    | "date_reading_style"
    | "price_reading_style"
    | "allow_interruptions"
    | "ai_disclosure_enabled"
    | "ai_disclosure_message"
  >
> = {
  "Recepcionista clínica formal": {
    voice_preset: "Recepcionista clínica formal",
    voice_instructions:
      "Tono profesional, claro y calmado. Vocaliza bien por teléfono y confirma datos sensibles con naturalidad.",
    speech_speed: "normal",
    pause_style: "natural",
    phone_reading_style: "groups",
    date_reading_style: "natural",
    price_reading_style: "clear",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual de la clínica.",
  },
  "Recepcionista cercana": {
    voice_preset: "Recepcionista cercana",
    voice_instructions:
      "Tono cálido, humano y cercano. Frases cortas, sonrisa en la voz y cero rigidez.",
    speech_speed: "normal",
    pause_style: "natural",
    phone_reading_style: "natural",
    date_reading_style: "natural",
    price_reading_style: "clear",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual, te ayudo con información y citas.",
  },
  "Peluquería/estética": {
    voice_preset: "Peluquería/estética",
    voice_instructions:
      "Tono ágil, amable y comercial suave. Suena como recepción de salón, cercana y resolutiva.",
    speech_speed: "fast",
    pause_style: "short",
    phone_reading_style: "groups",
    date_reading_style: "natural",
    price_reading_style: "brief",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy el asistente virtual del centro.",
  },
  "Clínica dental": {
    voice_preset: "Clínica dental",
    voice_instructions:
      "Tono sereno, profesional y tranquilizador. Evita dramatizar molestias y ofrece ayuda con citas.",
    speech_speed: "normal",
    pause_style: "natural",
    phone_reading_style: "groups",
    date_reading_style: "natural",
    price_reading_style: "clear",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual de la clínica dental.",
  },
  Fisioterapia: {
    voice_preset: "Fisioterapia",
    voice_instructions:
      "Tono cercano y seguro. Recoge motivo general sin sonar clínico ni dar indicaciones médicas.",
    speech_speed: "normal",
    pause_style: "natural",
    phone_reading_style: "groups",
    date_reading_style: "natural",
    price_reading_style: "clear",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual del centro.",
  },
  Psicología: {
    voice_preset: "Psicología",
    voice_instructions:
      "Tono pausado, respetuoso y discreto. Evita presión comercial y cuida la privacidad.",
    speech_speed: "slow",
    pause_style: "slow",
    phone_reading_style: "groups",
    date_reading_style: "natural",
    price_reading_style: "clear",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual del centro.",
  },
  "Centralita breve": {
    voice_preset: "Centralita breve",
    voice_instructions:
      "Tono muy breve y operativo. Responde rápido, resume y deriva cuando toque.",
    speech_speed: "fast",
    pause_style: "short",
    phone_reading_style: "digits",
    date_reading_style: "numeric",
    price_reading_style: "brief",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual.",
  },
  "Comercial suave": {
    voice_preset: "Comercial suave",
    voice_instructions:
      "Tono amable y proactivo, sin presión. Ayuda a cerrar una cita cuando el usuario muestra interés.",
    speech_speed: "normal",
    pause_style: "natural",
    phone_reading_style: "natural",
    date_reading_style: "natural",
    price_reading_style: "detailed",
    allow_interruptions: true,
    ai_disclosure_enabled: true,
    ai_disclosure_message: "Soy un asistente virtual del centro.",
  },
};

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

export function applyVoicePreset(
  current: AssistantConfigFormValues,
  preset: VoicePresetName,
): AssistantConfigFormValues {
  return {
    ...current,
    ...voicePresets[preset],
  };
}
