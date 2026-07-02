import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Pause,
  Play,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  Volume2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { previewAssistantVoice } from "@/api/assistants";
import { FormSection } from "@/components/common/FormSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  applyAssistantTemplate,
  assistantConfigDefaults,
  assistantConfigFormSchema,
  assistantTemplateNames,
  type AssistantConfigFormValues,
  type AssistantTemplateName,
} from "@/schemas/assistant";
import type { AssistantOptions } from "@/schemas/domain";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

type AssistantConfigTab =
  | "basic"
  | "voice"
  | "prompt"
  | "booking"
  | "safety"
  | "advanced"
  | "preview";

const assistantConfigTabs: Array<{
  id: AssistantConfigTab;
  label: string;
  help: string;
}> = [
  { id: "basic", label: "Básico", help: "Identidad y saludo" },
  { id: "voice", label: "Voz y modelo", help: "Modelo, voz y prueba" },
  { id: "prompt", label: "Prompt", help: "Prompt general" },
  { id: "booking", label: "Reservas", help: "Datos y agenda" },
  { id: "safety", label: "Seguridad", help: "Límites médicos" },
  { id: "advanced", label: "Avanzado", help: "Mensajes y privacidad" },
  { id: "preview", label: "Preview", help: "Vista final" },
];

export function AssistantConfigForm({
  clinicId,
  options,
  defaultValues = assistantConfigDefaults,
  contextWarnings = [],
  onSubmit,
  onCancel,
  isPending,
}: {
  clinicId: string;
  options: AssistantOptions;
  defaultValues?: AssistantConfigFormValues;
  contextWarnings?: string[];
  onSubmit: (values: AssistantConfigFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    watch,
    formState: { errors },
  } = useForm<AssistantConfigFormValues>({
    resolver: zodResolver(assistantConfigFormSchema),
    defaultValues,
  });
  const firstMessage = watch("first_message");
  const systemPrompt = watch("system_prompt");
  const realtimeVoice = watch("realtime_voice");
  const realtimeModel = watch("realtime_model");
  const maxPromptLength = 12000;
  const [activeTab, setActiveTab] = useState<AssistantConfigTab>("basic");
  const [voicePreviewText, setVoicePreviewText] = useState(
    "Hola, soy el asistente virtual. ¿En qué puedo ayudarle?",
  );
  const [voicePreviewStatus, setVoicePreviewStatus] = useState<
    "idle" | "generating" | "playing" | "paused"
  >("idle");
  const [voicePreviewError, setVoicePreviewError] = useState("");
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceAudioUrlRef = useRef<string | null>(null);
  const voiceAbortRef = useRef<AbortController | null>(null);
  const checklist = [
    {
      label: "Trabajadores activos",
      ok: !contextWarnings.includes("No hay trabajadores activos."),
      help: "Crea al menos un trabajador activo.",
    },
    {
      label: "Servicios reservables",
      ok: !contextWarnings.some((warning) =>
        warning.includes("No hay servicios reservables"),
      ),
      help: "Activa servicios reservables por bot.",
    },
    {
      label: "Calendario conectado",
      ok: !contextWarnings.includes("No hay calendario conectado."),
      help: "Conecta Google Calendar y enlaza calendarios.",
    },
    {
      label: "Número configurado",
      ok: !contextWarnings.includes("No hay número configurado."),
      help: "Añade un número activo para la clínica.",
    },
    {
      label: "Prompt suficiente",
      ok: systemPrompt.trim().length >= 40 && systemPrompt.length <= maxPromptLength,
      help: "Escribe un prompt claro, ni vacío ni enorme.",
    },
  ];

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  const stopVoicePreview = useCallback(() => {
    voiceAbortRef.current?.abort();
    voiceAbortRef.current = null;
    voiceAudioRef.current?.pause();
    voiceAudioRef.current = null;
    if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
    voiceAudioUrlRef.current = null;
    setVoicePreviewStatus("idle");
  }, []);

  useEffect(() => stopVoicePreview, [stopVoicePreview]);

  const playVoiceAudio = useCallback(async (audio: HTMLAudioElement) => {
    try {
      await audio.play();
      setVoicePreviewStatus("playing");
    } catch {
      setVoicePreviewStatus("paused");
      setVoicePreviewError(
        "El navegador bloqueó la reproducción automática. Pulsa reproducir.",
      );
    }
  }, []);

  const handleListenVoice = useCallback(async () => {
    const text = voicePreviewText.trim();
    if (!text) {
      setVoicePreviewError("Escribe una frase para probar la voz.");
      return;
    }
    voiceAbortRef.current?.abort();
    voiceAudioRef.current?.pause();
    if (voiceAudioUrlRef.current) URL.revokeObjectURL(voiceAudioUrlRef.current);
    voiceAudioRef.current = null;
    voiceAudioUrlRef.current = null;
    const controller = new AbortController();
    voiceAbortRef.current = controller;
    setVoicePreviewStatus("generating");
    setVoicePreviewError("");
    try {
      const blob = await previewAssistantVoice(
        clinicId,
        {
          text,
          realtime_voice: realtimeVoice,
          realtime_model: realtimeModel,
        },
        controller.signal,
      );
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => setVoicePreviewStatus("idle");
      audio.onpause = () => {
        if (!audio.ended) setVoicePreviewStatus("paused");
      };
      voiceAudioUrlRef.current = url;
      voiceAudioRef.current = audio;
      await playVoiceAudio(audio);
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      const message =
        error instanceof Error ? error.message : "No se pudo generar audio.";
      setVoicePreviewError(message);
      setVoicePreviewStatus("idle");
      toast.error(message);
    } finally {
      if (voiceAbortRef.current === controller) voiceAbortRef.current = null;
    }
  }, [clinicId, playVoiceAudio, realtimeModel, realtimeVoice, voicePreviewText]);

  const handleToggleVoiceAudio = useCallback(() => {
    const audio = voiceAudioRef.current;
    if (!audio) return;
    if (voicePreviewStatus === "playing") {
      audio.pause();
      return;
    }
    void playVoiceAudio(audio);
  }, [playVoiceAudio, voicePreviewStatus]);

  const handleRepeatVoiceAudio = useCallback(() => {
    const audio = voiceAudioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    void playVoiceAudio(audio);
  }, [playVoiceAudio]);

  return (
    <form className="space-y-7" onSubmit={handleSubmit(onSubmit)}>
      <div className="rounded-xl border border-[#dce4ff] bg-[#f8faff] p-4">
        <Label htmlFor="assistant-template">Plantilla rápida</Label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <Select
            id="assistant-template"
            defaultValue=""
            onChange={(event) => {
              const template = event.target.value as AssistantTemplateName;
              if (template) reset(applyAssistantTemplate(getValues(), template));
              event.target.value = "";
            }}
          >
            <option value="">Seleccionar plantilla…</option>
            {assistantTemplateNames.map((template) => (
              <option key={template} value={template}>
                {template}
              </option>
            ))}
          </Select>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              reset({
                ...getValues(),
                first_message: assistantConfigDefaults.first_message,
                system_prompt: assistantConfigDefaults.system_prompt,
                safety_prompt: assistantConfigDefaults.safety_prompt,
                booking_policy_prompt:
                  assistantConfigDefaults.booking_policy_prompt,
                cancellation_policy_prompt:
                  assistantConfigDefaults.cancellation_policy_prompt,
                transfer_policy_prompt:
                  assistantConfigDefaults.transfer_policy_prompt,
                tone: assistantConfigDefaults.tone,
                response_length: assistantConfigDefaults.response_length,
                ask_patient_name: assistantConfigDefaults.ask_patient_name,
                ask_patient_phone: assistantConfigDefaults.ask_patient_phone,
                ask_general_reason: assistantConfigDefaults.ask_general_reason,
                allow_booking_without_worker:
                  assistantConfigDefaults.allow_booking_without_worker,
                max_proposed_slots: assistantConfigDefaults.max_proposed_slots,
                allow_cancellations: assistantConfigDefaults.allow_cancellations,
                allow_reschedules: assistantConfigDefaults.allow_reschedules,
                natural_confirmation_required:
                  assistantConfigDefaults.natural_confirmation_required,
                avoid_exact_confirmation_phrases:
                  assistantConfigDefaults.avoid_exact_confirmation_phrases,
                additional_instructions:
                  assistantConfigDefaults.additional_instructions,
                forbidden_phrases: assistantConfigDefaults.forbidden_phrases,
                no_availability_message:
                  assistantConfigDefaults.no_availability_message,
                missing_calendar_message:
                  assistantConfigDefaults.missing_calendar_message,
                emergency_message: assistantConfigDefaults.emergency_message,
                human_transfer_message:
                  assistantConfigDefaults.human_transfer_message,
                closing_message: assistantConfigDefaults.closing_message,
                use_prices: assistantConfigDefaults.use_prices,
                use_knowledge_base: assistantConfigDefaults.use_knowledge_base,
                strict_calendar_mode:
                  assistantConfigDefaults.strict_calendar_mode,
              })
            }
          >
            <RefreshCcw className="size-4" />
            Restaurar prompt recomendado
          </Button>
        </div>
        <p className="mt-2 text-xs text-[#6f7c92]">
          Cambia saludo y prompts. Conserva nombre, modelo, voz, estado,
          privacidad y retención.
        </p>
      </div>
      <div
        role="tablist"
        aria-label="Secciones de configuraciÃ³n del asistente"
        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7"
      >
        {assistantConfigTabs.map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveTab(tab.id)}
              className={`rounded-xl border px-3 py-2 text-left transition ${
                selected
                  ? "border-[#315efb] bg-[#eef2ff] text-[#1d3fb7] shadow-sm"
                  : "border-[#dfe4ec] bg-white text-[#526078] hover:bg-[#f7f9fc]"
              }`}
            >
              <span className="block text-sm font-semibold">{tab.label}</span>
              <span className="mt-0.5 block text-xs opacity-75">
                {tab.help}
              </span>
            </button>
          );
        })}
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-7">
          <div className={activeTab === "basic" ? "contents" : "hidden"}>
          <FormSection
            title="1. Identidad del asistente"
            description="Nombre interno, idioma, tono y longitud de respuesta."
          >
            <div>
              <Label htmlFor="assistant-name">Nombre de configuración</Label>
              <Input
                id="assistant-name"
                className="mt-1.5"
                {...register("name")}
              />
              <FieldError message={errors.name?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-language">Idioma</Label>
              <Select
                id="assistant-language"
                className="mt-1.5"
                {...register("language")}
              >
                {options.languages.map((language) => (
                  <option key={language.id} value={language.id}>
                    {language.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-tone">Tono</Label>
              <Select id="assistant-tone" className="mt-1.5" {...register("tone")}>
                <option value="profesional">Profesional</option>
                <option value="cercano">Cercano</option>
                <option value="comercial">Comercial</option>
                <option value="breve">Breve</option>
                <option value="formal">Formal</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="assistant-response-length">
                Longitud de respuesta
              </Label>
              <Select
                id="assistant-response-length"
                className="mt-1.5"
                {...register("response_length")}
              >
                <option value="corta">Corta</option>
                <option value="normal">Normal</option>
                <option value="detallada">Detallada</option>
              </Select>
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "voice" ? "contents" : "hidden"}>
          <FormSection
            title="2. Voz y modelo"
            description="Opciones permitidas por la configuración del backend."
          >
            <div>
              <Label htmlFor="assistant-model">Modelo Realtime</Label>
              <Select
                id="assistant-model"
                className="mt-1.5"
                {...register("realtime_model")}
              >
                {options.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </Select>
              <FieldError message={errors.realtime_model?.message} />
            </div>
            <div>
              <Label htmlFor="assistant-voice">Voz</Label>
              <Select
                id="assistant-voice"
                className="mt-1.5"
                {...register("realtime_voice")}
              >
                {options.voices.map((voice) => (
                  <option key={voice.id} value={voice.id}>
                    {voice.label}
                  </option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-[#7d8899]">
                Para España o galego, controla idioma y acento desde el prompt.
                Marin y Cedar quedan como voces recomendadas.
              </p>
            </div>
            <div>
              <Label htmlFor="assistant-temperature">Temperatura opcional</Label>
              <Input
                id="assistant-temperature"
                type="number"
                min="0"
                max="2"
                step="0.1"
                className="mt-1.5"
                {...register("temperature")}
              />
              <FieldError message={errors.temperature?.message} />
            </div>
            <label className="mt-6 flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
              <input
                type="checkbox"
                className="size-4 accent-[#315efb]"
                {...register("is_active")}
              />
              Activar al guardar
            </label>
            <div className="sm:col-span-2 rounded-xl border border-[#dce4ff] bg-[#f8faff] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-[#27334a]">
                    <Volume2 className="size-4 text-[#315efb]" />
                    Probar voz
                  </div>
                  <p className="mt-1 text-xs leading-5 text-[#6f7c92]">
                    Genera un MP3 corto con la voz seleccionada. Usa los valores
                    actuales del formulario, aunque todavÃ­a no hayas guardado.
                  </p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-[#526078]">
                  {realtimeVoice} Â· {realtimeModel}
                </span>
              </div>
              <div className="mt-3">
                <Label htmlFor="assistant-voice-preview">Frase de prueba</Label>
                <Textarea
                  id="assistant-voice-preview"
                  value={voicePreviewText}
                  onChange={(event) => setVoicePreviewText(event.target.value)}
                  className="mt-1.5 min-h-24"
                  maxLength={500}
                />
                <p className="mt-1 text-xs text-[#7d8899]">
                  {voicePreviewText.length}/500 caracteres. Esta prueba no crea
                  conversaciÃ³n ni se guarda.
                </p>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  onClick={() => void handleListenVoice()}
                  disabled={voicePreviewStatus === "generating"}
                >
                  <Volume2 className="size-4" />
                  {voicePreviewStatus === "generating"
                    ? "Generando..."
                    : "Escuchar"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleToggleVoiceAudio}
                  disabled={
                    voicePreviewStatus === "generating" || !voiceAudioRef.current
                  }
                >
                  {voicePreviewStatus === "playing" ? (
                    <Pause className="size-4" />
                  ) : (
                    <Play className="size-4" />
                  )}
                  {voicePreviewStatus === "playing" ? "Pausar" : "Reproducir"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleRepeatVoiceAudio}
                  disabled={
                    voicePreviewStatus === "generating" || !voiceAudioRef.current
                  }
                >
                  <RefreshCcw className="size-4" />
                  Repetir
                </Button>
                <span className="text-xs font-medium text-[#6f7c92]">
                  {voicePreviewStatus === "generating"
                    ? "generando audio"
                    : voicePreviewStatus === "playing"
                      ? "reproduciendo"
                      : voicePreviewStatus === "paused"
                        ? "pausado"
                        : "listo"}
                </span>
              </div>
              {voicePreviewError ? (
                <p className="mt-2 text-xs font-medium text-[#bd3341]">
                  {voicePreviewError}
                </p>
              ) : null}
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "basic" ? "contents" : "hidden"}>
          <FormSection
            title="3. Primer mensaje"
            description="Saludo que verá también la consola de prueba."
          >
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-first-message">Primer mensaje</Label>
              <Textarea
                id="assistant-first-message"
                className="mt-1.5 min-h-28"
                {...register("first_message")}
              />
              <FieldError message={errors.first_message?.message} />
            </div>
            <div className="sm:col-span-2 rounded-xl border bg-[#fbfcfe] p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase text-[#7a8598]">
                <Volume2 className="size-4" />
                Preview del primer mensaje
              </div>
              <p className="mt-2 text-sm leading-6 text-[#47546a]">
                {firstMessage || "El saludo aparecerá aquí."}
              </p>
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "prompt" ? "contents" : "hidden"}>
          <FormSection
            title="4. Prompt general editable"
            description="La base de comportamiento del asistente antes de añadir servicios y contexto real."
          >
            <div className="sm:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="assistant-system-prompt">Prompt general</Label>
                <span
                  className={`text-xs ${
                    systemPrompt.length > maxPromptLength ||
                    systemPrompt.trim().length < 40
                      ? "text-[#bd3341]"
                      : "text-[#7d8899]"
                  }`}
                >
                  {systemPrompt.length}/{maxPromptLength} caracteres
                </span>
              </div>
              <Textarea
                id="assistant-system-prompt"
                className="mt-1.5 min-h-64 font-mono text-sm"
                {...register("system_prompt")}
              />
              <FieldError message={errors.system_prompt?.message} />
              {systemPrompt.trim().length < 40 ? (
                <p className="mt-1 text-xs text-[#bd3341]">
                  El prompt parece demasiado corto.
                </p>
              ) : null}
              {systemPrompt.length > maxPromptLength ? (
                <p className="mt-1 text-xs text-[#bd3341]">
                  El prompt es demasiado largo para mantenerlo operativo.
                </p>
              ) : null}
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "booking" ? "contents" : "hidden"}>
          <FormSection
            title="5. Reglas de reservas"
            description="Qué datos pide y cómo usa agenda y herramientas."
          >
            <div className="sm:col-span-2 grid gap-2 md:grid-cols-2">
              {([
                { name: "ask_patient_name", label: "Pedir nombre" },
                { name: "ask_patient_phone", label: "Pedir teléfono" },
                { name: "ask_general_reason", label: "Pedir motivo general" },
                {
                  name: "allow_booking_without_worker",
                  label: "Permitir reservar sin trabajador concreto",
                },
                { name: "allow_cancellations", label: "Permitir cancelaciones" },
                { name: "allow_reschedules", label: "Permitir cambios de cita" },
                {
                  name: "natural_confirmation_required",
                  label: "Pedir confirmación natural antes de reservar",
                },
                {
                  name: "avoid_exact_confirmation_phrases",
                  label: "No pedir frases exactas",
                },
              ] as const).map(({ name, label }) => (
                <label
                  key={name}
                  className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-[#315efb]"
                    {...register(name)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div>
              <Label htmlFor="assistant-max-slots">
                Número máximo de horarios a proponer
              </Label>
              <Input
                id="assistant-max-slots"
                type="number"
                min="1"
                max="10"
                className="mt-1.5"
                {...register("max_proposed_slots", { valueAsNumber: true })}
              />
              <FieldError message={errors.max_proposed_slots?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-booking-policy">Política de reservas</Label>
              <Textarea
                id="assistant-booking-policy"
                className="mt-1.5 min-h-36"
                {...register("booking_policy_prompt")}
              />
              <FieldError message={errors.booking_policy_prompt?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-cancellation-policy">
                Política de cancelación
              </Label>
              <Textarea
                id="assistant-cancellation-policy"
                className="mt-1.5 min-h-32"
                {...register("cancellation_policy_prompt")}
              />
              <FieldError message={errors.cancellation_policy_prompt?.message} />
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "safety" ? "contents" : "hidden"}>
          <FormSection
            title="6. Seguridad médica"
            description="Restricciones que siempre se añaden al prompt final."
          >
            <div className="sm:col-span-2">
              <div className="mb-2 flex items-center gap-2 text-sm text-[#8c4b15]">
                <ShieldAlert className="size-4" />
                No elimines el protocolo de urgencias.
              </div>
              <Textarea
                aria-label="Prompt de seguridad"
                className="min-h-44"
                {...register("safety_prompt")}
              />
              <FieldError message={errors.safety_prompt?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-emergency-message">
                Mensaje si hay urgencia médica
              </Label>
              <Textarea
                id="assistant-emergency-message"
                className="mt-1.5 min-h-24"
                {...register("emergency_message")}
              />
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "advanced" ? "contents" : "hidden"}>
          <FormSection
            title="7. Transferencia a humano"
            description="Cuándo debe pedir ayuda humana y qué dice."
          >
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-transfer-policy">
                Política de transferencia
              </Label>
              <Textarea
                id="assistant-transfer-policy"
                className="mt-1.5 min-h-36"
                {...register("transfer_policy_prompt")}
              />
              <FieldError message={errors.transfer_policy_prompt?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-human-transfer-message">
                Mensaje de transferencia a humano
              </Label>
              <Textarea
                id="assistant-human-transfer-message"
                className="mt-1.5 min-h-24"
                {...register("human_transfer_message")}
              />
            </div>
          </FormSection>

          <FormSection
            title="8. Configuración avanzada"
            description="Mensajes operativos, privacidad y uso del contexto."
          >
            <div className="sm:col-span-2 grid gap-2 md:grid-cols-2">
              {([
                { name: "use_prices", label: "Usar precios en el prompt" },
                { name: "use_knowledge_base", label: "Usar knowledge base" },
                { name: "transcript_enabled", label: "Guardar transcripción" },
                { name: "recording_enabled", label: "Habilitar grabación" },
                {
                  name: "strict_calendar_mode",
                  label: "Modo estricto de calendario",
                },
              ] as const).map(({ name, label }) => (
                <label
                  key={name}
                  className="flex min-h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-[#315efb]"
                    {...register(name)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div>
              <Label htmlFor="assistant-retention">Retención (días)</Label>
              <Input
                id="assistant-retention"
                type="number"
                min="1"
                max="3650"
                className="mt-1.5"
                {...register("conversation_retention_days", {
                  valueAsNumber: true,
                })}
              />
              <FieldError message={errors.conversation_retention_days?.message} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-additional-instructions">
                Instrucciones adicionales libres
              </Label>
              <Textarea
                id="assistant-additional-instructions"
                className="mt-1.5 min-h-28"
                {...register("additional_instructions")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-forbidden-phrases">
                Palabras/frases prohibidas
              </Label>
              <Textarea
                id="assistant-forbidden-phrases"
                className="mt-1.5 min-h-24"
                placeholder="Una por línea"
                {...register("forbidden_phrases")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-no-availability">
                Mensaje si no hay disponibilidad
              </Label>
              <Textarea
                id="assistant-no-availability"
                className="mt-1.5 min-h-24"
                {...register("no_availability_message")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-missing-calendar">
                Mensaje si falta calendario
              </Label>
              <Textarea
                id="assistant-missing-calendar"
                className="mt-1.5 min-h-24"
                {...register("missing_calendar_message")}
              />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="assistant-closing-message">
                Mensaje de cierre de llamada/chat
              </Label>
              <Textarea
                id="assistant-closing-message"
                className="mt-1.5 min-h-20"
                {...register("closing_message")}
              />
            </div>
            <div className="sm:col-span-2 rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-3 text-xs leading-5 text-[#78591d]">
              La preferencia de grabación se persiste, pero este MVP todavía no
              captura ni almacena audio.
            </div>
          </FormSection>
          </div>

          <div className={activeTab === "preview" ? "contents" : "hidden"}>
          <div className="rounded-xl border bg-[#fbfcfe] p-4">
            <div className="flex items-center gap-2 font-semibold text-[#27334a]">
              <Bot className="size-4 text-[#315efb]" />
              9. Preview final del prompt
            </div>
            <p className="mt-1 text-sm text-[#6f7c92]">
              Guarda la configuración y usa “Previsualizar prompt final” en la
              tarjeta para renderizarlo con servicios, trabajadores y knowledge
              reales de la clínica.
            </p>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl border bg-white p-3">
                <p className="text-xs font-semibold uppercase text-[#7a8598]">
                  Primer mensaje
                </p>
                <p className="mt-2 text-sm leading-6 text-[#47546a]">
                  {firstMessage || "El saludo aparecerÃ¡ aquÃ­."}
                </p>
              </div>
              <div className="rounded-xl border bg-white p-3">
                <p className="text-xs font-semibold uppercase text-[#7a8598]">
                  Prompt general actual
                </p>
                <p className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-5 text-[#47546a]">
                  {systemPrompt || "El prompt general aparecerÃ¡ aquÃ­."}
                </p>
              </div>
            </div>
          </div>
          </div>
        </div>

        <aside className="h-fit rounded-2xl border bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 font-semibold text-[#27334a]">
            <CheckCircle2 className="size-4 text-[#315efb]" />
            Estado de configuración
          </div>
          <div className="mt-4 space-y-3">
            {checklist.map((item) => (
              <div key={item.label} className="flex items-start gap-2">
                {item.ok ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[#168a53]" />
                ) : (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[#c77a10]" />
                )}
                <div>
                  <p className="text-sm font-medium text-[#27334a]">
                    {item.label}
                  </p>
                  {!item.ok ? (
                    <p className="text-xs leading-5 text-[#7a8598]">
                      {item.help}
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          {contextWarnings.length ? (
            <div className="mt-4 rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-3 text-xs leading-5 text-[#78591d]">
              {contextWarnings.slice(0, 4).map((warning) => (
                <p key={warning}>• {warning}</p>
              ))}
            </div>
          ) : null}
        </aside>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending}>
          <Sparkles className="size-4" />
          {isPending ? "Guardando…" : "Guardar configuración"}
        </Button>
      </div>
    </form>
  );
}
