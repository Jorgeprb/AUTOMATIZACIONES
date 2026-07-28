import { zodResolver } from "@hookform/resolvers/zod";
import { useQueries } from "@tanstack/react-query";
import { Play, Save, Volume2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import {
  listVoiceProviderVoices,
  previewAssistantVoice,
} from "@/api/assistants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  assistantConfigDefaults,
  assistantConfigFormSchema,
  type AssistantConfigFormValues,
  type AssistantConfigPayload,
} from "@/schemas/assistant";
import type {
  AssistantOptions,
  VoiceCatalogVoice,
  VoiceProviderInfo,
} from "@/schemas/domain";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

function SwitchField({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 rounded-xl border border-[#e4e8ef] bg-white p-4">
      <span>
        <span className="block text-sm font-semibold text-[#27334a]">{label}</span>
        {description ? (
          <span className="mt-1 block text-xs leading-5 text-[#748095]">
            {description}
          </span>
        ) : null}
      </span>
      <input
        type="checkbox"
        className="mt-1 size-5 shrink-0 accent-[#315efb]"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[#e4e8ef] bg-[#fbfcfe] p-5 md:p-6">
      <div className="mb-5">
        <h3 className="text-lg font-bold text-[#27334a]">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-[#748095]">{description}</p>
      </div>
      {children}
    </section>
  );
}

interface VoiceChoice {
  key: string;
  provider: string;
  providerName: string;
  voiceId: string;
  label: string;
  model: string;
  locale: string | null;
  gender: string | null;
  requiresConsent: boolean;
  recommended: boolean;
}

function providerName(
  provider: string,
  providers: VoiceProviderInfo[],
): string {
  return (
    providers.find((item) => item.id === provider)?.display_name ?? provider
  );
}

function speechSpeedForMultiplier(value: string): "slow" | "normal" | "fast" {
  const multiplier = Number(value);
  if (multiplier < 0.9) return "slow";
  if (multiplier > 1.15) return "fast";
  return "normal";
}

function buildConfigPayload(
  values: AssistantConfigFormValues,
): AssistantConfigPayload {
  return {
    ...values,
    // The stable local bridge supports both OpenAI audio and external TTS.
    // Keep the routing decision out of the user-facing configuration.
    call_audio_mode: "vps_media_bridge",
    speech_speed: speechSpeedForMultiplier(values.voice_speed),
    temperature: values.temperature || null,
    turn_end_silence_ms: Number(values.turn_end_silence_ms),
    idle_timeout_ms: values.idle_timeout_ms
      ? Number(values.idle_timeout_ms)
      : null,
    tts_model: values.tts_model.trim() || null,
    voice_id: values.voice_id.trim() || null,
    voice_locale: values.voice_locale.trim() || null,
    voice_gender: values.voice_gender.trim() || null,
    azure_speech_region: values.azure_speech_region.trim() || null,
    voice_style: values.voice_style.trim() || null,
    voice_stability: values.voice_stability || null,
    voice_similarity: values.voice_similarity || null,
    voice_temperature: values.voice_temperature || null,
  };
}

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
  assistantConfigId?: string | null;
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
    setValue,
    watch,
    formState: { errors },
  } = useForm<AssistantConfigFormValues>({
    resolver: zodResolver(assistantConfigFormSchema),
    defaultValues,
  });

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  const configuredProviders = useMemo(
    () =>
      options.voice_providers.filter(
        (provider) => provider.enabled && provider.configured,
      ),
    [options.voice_providers],
  );
  const voiceQueries = useQueries({
    queries: configuredProviders.map((provider) => ({
      queryKey: ["voice-provider-voices", provider.id],
      queryFn: () => listVoiceProviderVoices(provider.id),
      staleTime: 1000 * 60 * 10,
    })),
  });

  const voiceChoices = useMemo<VoiceChoice[]>(() => {
    const catalog: VoiceCatalogVoice[] = voiceQueries.flatMap(
      (query) => query.data ?? [],
    );
    const choices = catalog
      .filter((voice) => voice.enabled)
      .map((voice) => ({
        key: `${voice.provider}::${voice.voice_id}`,
        provider: voice.provider,
        providerName: providerName(voice.provider, options.voice_providers),
        voiceId: voice.voice_id,
        label: voice.display_name,
        model: voice.model,
        locale: voice.locale,
        gender: voice.gender,
        requiresConsent: voice.requires_consent,
        recommended: voice.recommended,
      }));

    for (const voice of options.voices) {
      const key = `openai::${voice.id}`;
      if (!choices.some((choice) => choice.key === key)) {
        choices.push({
          key,
          provider: "openai",
          providerName: "OpenAI",
          voiceId: voice.id,
          label: voice.label,
          model: options.default_model,
          locale: null,
          gender: null,
          requiresConsent: false,
          recommended: voice.recommended,
        });
      }
    }
    return choices.sort((a, b) => {
      if (a.recommended !== b.recommended) return a.recommended ? -1 : 1;
      return a.label.localeCompare(b.label, "es");
    });
  }, [options, voiceQueries]);

  const voiceProvider = watch("voice_provider");
  const realtimeVoice = watch("realtime_voice");
  const voiceId = watch("voice_id");
  const selectedVoiceKey = `${voiceProvider}::${
    voiceProvider === "openai" ? realtimeVoice : voiceId
  }`;
  const selectedVoice = voiceChoices.find(
    (voice) => voice.key === selectedVoiceKey,
  );

  const allowInterruptions = watch("allow_interruptions");
  const allowBookings = watch("allow_bookings");
  const transcriptEnabled = watch("transcript_enabled");
  const useKnowledgeBase = watch("use_knowledge_base");
  const aiDisclosureEnabled = watch("ai_disclosure_enabled");
  const [previewText, setPreviewText] = useState(
    defaultValues.first_message || assistantConfigDefaults.first_message,
  );
  const [previewing, setPreviewing] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    setPreviewText(defaultValues.first_message || assistantConfigDefaults.first_message);
  }, [defaultValues.first_message]);

  useEffect(
    () => () => {
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    },
    [],
  );

  const changeVoice = (key: string) => {
    const choice = voiceChoices.find((voice) => voice.key === key);
    if (!choice) return;
    setValue("voice_provider", choice.provider, { shouldDirty: true });
    setValue("call_audio_mode", "vps_media_bridge");
    setValue("realtime_model", options.default_model);
    if (choice.provider === "openai") {
      setValue("realtime_voice", choice.voiceId);
      setValue("voice_id", "");
      setValue("tts_model", "");
    } else {
      setValue("voice_id", choice.voiceId);
      setValue("tts_model", choice.model || "");
      setValue("voice_locale", choice.locale || getValues("language"));
      setValue("voice_gender", choice.gender || "");
    }
    setValue("external_voice_legal_confirmed", !choice.requiresConsent);
  };

  const playPreview = async () => {
    const text = previewText.trim();
    if (!text) {
      toast.error("Escribe una frase para escuchar la voz");
      return;
    }
    setPreviewing(true);
    try {
      const values = getValues();
      const payload = buildConfigPayload(values);
      const blob = await previewAssistantVoice(clinicId, {
        text,
        realtime_voice: payload.realtime_voice,
        realtime_model: payload.realtime_model,
        call_audio_mode: payload.call_audio_mode,
        voice_provider: payload.voice_provider,
        tts_model: payload.tts_model,
        voice_id: payload.voice_id,
        voice_locale: payload.voice_locale,
        voice_gender: payload.voice_gender,
        azure_speech_region: payload.azure_speech_region,
        voice_style: payload.voice_style,
        voice_speed: payload.voice_speed,
        voice_pitch: payload.voice_pitch,
        output_audio_format: payload.output_audio_format,
        telephony_codec: payload.telephony_codec,
        external_voice_legal_confirmed:
          payload.external_voice_legal_confirmed,
        voice_instructions: payload.voice_instructions,
        speech_speed: payload.speech_speed,
        pause_style: payload.pause_style,
        phone_reading_style: payload.phone_reading_style,
        date_reading_style: payload.date_reading_style,
        price_reading_style: payload.price_reading_style,
        allow_interruptions: payload.allow_interruptions,
        idle_timeout_ms: payload.idle_timeout_ms,
        ai_disclosure_enabled: payload.ai_disclosure_enabled,
        ai_disclosure_message: payload.ai_disclosure_message,
        preview_audio_format: payload.preview_audio_format,
      });
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      const url = URL.createObjectURL(blob);
      audioUrlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      await audio.play();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "No se pudo generar la voz");
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <form
      className="space-y-6"
      onSubmit={handleSubmit(async (values) => onSubmit(values))}
    >
      {contextWarnings.length ? (
        <div className="rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-4 text-sm text-[#78591d]">
          {contextWarnings.map((warning) => (
            <p key={warning}>• {warning}</p>
          ))}
        </div>
      ) : null}

      <Section
        title="Identidad y voz"
        description="Lo que la persona escucha y cómo suena el asistente. Los detalles técnicos se configuran automáticamente."
      >
        <div className="grid gap-5 md:grid-cols-2">
          <div>
            <Label htmlFor="assistant-name">Nombre de esta configuración</Label>
            <Input id="assistant-name" {...register("name")} />
            <FieldError message={errors.name?.message} />
          </div>
          <div>
            <Label htmlFor="assistant-language">Idioma principal</Label>
            <Select id="assistant-language" {...register("language")}>
              {options.languages.map((language) => (
                <option key={language.id} value={language.id}>
                  {language.label}
                </option>
              ))}
            </Select>
            <FieldError message={errors.language?.message} />
          </div>
          <div className="md:col-span-2">
            <Label htmlFor="assistant-voice">Voz</Label>
            <Select
              id="assistant-voice"
              value={selectedVoiceKey}
              onChange={(event) => changeVoice(event.target.value)}
            >
              {!selectedVoice ? (
                <option value={selectedVoiceKey}>
                  {voiceId || realtimeVoice || "Voz actual"}
                </option>
              ) : null}
              {voiceChoices.map((voice) => (
                <option key={voice.key} value={voice.key}>
                  {voice.label}
                  {voice.locale ? ` · ${voice.locale}` : ""}
                  {voice.recommended ? " · recomendada" : ""}
                </option>
              ))}
            </Select>
            <p className="mt-1 text-xs text-[#748095]">
              El proveedor, el modelo, el codec y el modo de llamada se resuelven por detrás.
            </p>
          </div>
          {selectedVoice?.requiresConsent ? (
            <div className="md:col-span-2">
              <SwitchField
                label="Confirmo que tengo derecho a utilizar esta voz"
                checked={watch("external_voice_legal_confirmed")}
                onChange={(checked) =>
                  setValue("external_voice_legal_confirmed", checked)
                }
              />
              <FieldError
                message={errors.external_voice_legal_confirmed?.message}
              />
            </div>
          ) : null}
          <div className="md:col-span-2">
            <Label htmlFor="first-message">Frase de bienvenida</Label>
            <Textarea
              id="first-message"
              rows={3}
              {...register("first_message")}
            />
            <FieldError message={errors.first_message?.message} />
          </div>
          <div className="md:col-span-2 rounded-xl border border-[#e4e8ef] bg-white p-4">
            <div className="mb-3 flex items-center gap-2 font-semibold text-[#27334a]">
              <Volume2 className="size-4" /> Escuchar la voz
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input
                value={previewText}
                onChange={(event) => setPreviewText(event.target.value)}
                placeholder="Escribe una frase de prueba"
              />
              <Button
                type="button"
                variant="outline"
                disabled={previewing}
                onClick={() => void playPreview()}
              >
                <Play className="size-4" />
                {previewing ? "Generando…" : "Escuchar"}
              </Button>
            </div>
          </div>
        </div>
      </Section>

      <Section
        title="Naturalidad de la conversación"
        description="Ajustes que sí cambian la forma de hablar, escuchar y reaccionar."
      >
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          <div>
            <Label>Tono</Label>
            <Select {...register("tone")}>
              <option value="cercano">Cercano</option>
              <option value="profesional">Profesional</option>
              <option value="formal">Formal</option>
              <option value="comercial">Comercial suave</option>
              <option value="breve">Muy directo</option>
            </Select>
          </div>
          <div>
            <Label>Longitud de respuesta</Label>
            <Select {...register("response_length")}>
              <option value="corta">Corta</option>
              <option value="normal">Natural</option>
              <option value="detallada">Detallada</option>
            </Select>
          </div>
          <div>
            <Label>Iniciativa</Label>
            <Select {...register("initiative_level")}>
              <option value="bajo">Espera indicaciones</option>
              <option value="medio">Equilibrada</option>
              <option value="alto">Proactiva</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="assistant-voice-speed">Velocidad de voz</Label>
            <Input
              id="assistant-voice-speed"
              type="number"
              min={0.5}
              max={2}
              step={0.05}
              inputMode="decimal"
              {...register("voice_speed")}
            />
            <p className="mt-1 text-xs text-[#657087]">
              Multiplicador: 1.00 es normal, 1.20 es un 20 % más rápida.
            </p>
            <FieldError message={errors.voice_speed?.message} />
          </div>
          <div>
            <Label htmlFor="assistant-temperature">Temperatura del modelo</Label>
            <Input
              id="assistant-temperature"
              type="number"
              min={0.6}
              max={1.2}
              step={0.05}
              inputMode="decimal"
              {...register("temperature")}
            />
            <p className="mt-1 text-xs text-[#657087]">
              0.80 es equilibrada; valores bajos son más consistentes y los altos más variados.
            </p>
            <FieldError message={errors.temperature?.message} />
          </div>
          <div>
            <Label htmlFor="assistant-turn-end">Espera al terminar de hablar</Label>
            <Input
              id="assistant-turn-end"
              type="number"
              min={200}
              max={1200}
              step={50}
              inputMode="numeric"
              {...register("turn_end_silence_ms")}
            />
            <p className="mt-1 text-xs text-[#657087]">
              Milisegundos de silencio antes de responder. 300–400 ms suele sentirse ágil.
            </p>
            <FieldError message={errors.turn_end_silence_ms?.message} />
          </div>
          <div>
            <Label>Pausas</Label>
            <Select {...register("pause_style")}>
              <option value="short">Cortas</option>
              <option value="natural">Naturales</option>
              <option value="slow">Pausadas</option>
            </Select>
          </div>
          <div>
            <Label>Preguntas seguidas como máximo</Label>
            <Input
              type="number"
              min={1}
              max={5}
              {...register("max_consecutive_questions", {
                valueAsNumber: true,
              })}
            />
          </div>
          <div>
            <Label>Repreguntar tras silencio</Label>
            <Select {...register("idle_timeout_ms")}>
              <option value="">No repreguntar automáticamente</option>
              <option value="8000">A los 8 segundos</option>
              <option value="12000">A los 12 segundos</option>
              <option value="20000">A los 20 segundos</option>
            </Select>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <SwitchField
            label="Permitir que la persona interrumpa al asistente"
            description="El bot se calla cuando detecta que la persona empieza a hablar y escucha la nueva intervención."
            checked={allowInterruptions}
            onChange={(checked) => setValue("allow_interruptions", checked)}
          />
          <SwitchField
            label="Aceptar confirmaciones naturales"
            description="Entiende «vale», «esa me sirve» o «resérvala» sin exigir una frase exacta."
            checked={watch("natural_confirmation_required")}
            onChange={(checked) =>
              setValue("natural_confirmation_required", checked)
            }
          />
          <SwitchField
            label="Avisar de que es un asistente virtual"
            checked={aiDisclosureEnabled}
            onChange={(checked) => setValue("ai_disclosure_enabled", checked)}
          />
          <SwitchField
            label="Evitar confirmaciones repetitivas"
            checked={watch("avoid_exact_confirmation_phrases")}
            onChange={(checked) =>
              setValue("avoid_exact_confirmation_phrases", checked)
            }
          />
        </div>
        {aiDisclosureEnabled ? (
          <div className="mt-4">
            <Label>Texto de transparencia</Label>
            <Input {...register("ai_disclosure_message")} />
          </div>
        ) : null}
        <div className="mt-4">
          <Label>Indicaciones sobre la forma de hablar</Label>
          <Textarea
            rows={3}
            {...register("voice_instructions")}
            placeholder="Ej.: voz cálida, nada robótica, frases cortas y sonrisa al hablar."
          />
        </div>
      </Section>

      <Section
        title="Citas y datos que debe pedir"
        description="Controla qué puede gestionar y qué información necesita recoger."
      >
        <div className="grid gap-3 md:grid-cols-2">
          <SwitchField
            label="Gestionar reservas"
            checked={allowBookings}
            onChange={(checked) => setValue("allow_bookings", checked)}
          />
          <SwitchField
            label="Cambiar citas"
            checked={watch("allow_reschedules")}
            onChange={(checked) => setValue("allow_reschedules", checked)}
          />
          <SwitchField
            label="Cancelar citas"
            checked={watch("allow_cancellations")}
            onChange={(checked) => setValue("allow_cancellations", checked)}
          />
          <SwitchField
            label="Responder precios publicados"
            checked={watch("allow_price_answers")}
            onChange={(checked) => setValue("allow_price_answers", checked)}
          />
          <SwitchField
            label="Pedir el nombre"
            checked={watch("ask_patient_name")}
            onChange={(checked) => setValue("ask_patient_name", checked)}
          />
          <SwitchField
            label="Pedir o confirmar el teléfono"
            checked={watch("ask_patient_phone")}
            onChange={(checked) => setValue("ask_patient_phone", checked)}
          />
          <div className="rounded-xl border border-[#e4e8ef] bg-white p-4">
            <Label>Cómo identificar el servicio</Label>
            <Select
              className="mt-2"
              {...register("service_prompt_mode")}
              onChange={(event) => {
                const mode = event.target.value as
                  | "list_services"
                  | "ask_open"
                  | "infer_confirm";
                setValue("service_prompt_mode", mode);
                setValue("ask_service", mode !== "infer_confirm");
              }}
            >
              <option value="list_services">
                Listar los servicios disponibles
              </option>
              <option value="ask_open">
                Preguntar qué servicio necesita
              </option>
              <option value="infer_confirm">
                Inferirlo y confirmarlo: «¿Para cortar el pelo?»
              </option>
            </Select>
            <p className="mt-2 text-xs leading-5 text-[#748095]">
              En el modo inferido solo confirma un servicio cuando la intención es
              clara; si no, pregunta sin inventar.
            </p>
          </div>
          <SwitchField
            label="Pedir un motivo general"
            description="Solo una descripción breve; nunca historia clínica."
            checked={watch("ask_general_reason")}
            onChange={(checked) => setValue("ask_general_reason", checked)}
          />
          <SwitchField
            label="Buscar con cualquier profesional disponible"
            checked={watch("allow_booking_without_worker")}
            onChange={(checked) =>
              setValue("allow_booking_without_worker", checked)
            }
          />
          <SwitchField
            label="Usar disponibilidad real de calendario"
            checked={watch("strict_calendar_mode")}
            onChange={(checked) => setValue("strict_calendar_mode", checked)}
          />
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div>
            <Label>Intervalo entre horas que se pueden ofrecer</Label>
            <Select
              className="mt-2"
              {...register("slot_interval_minutes", { valueAsNumber: true })}
            >
              <option value={5}>Cada 5 minutos</option>
              <option value={10}>Cada 10 minutos</option>
              <option value={15}>Cada 15 minutos</option>
              <option value={20}>Cada 20 minutos</option>
              <option value={30}>Cada 30 minutos</option>
              <option value={60}>Cada 60 minutos</option>
            </Select>
            <p className="mt-2 text-xs leading-5 text-[#748095]">
              Por ejemplo, con 30 minutos solo se ofrecerán horas en punto y a y
              media; nunca a y cuarto.
            </p>
          </div>
          <div>
            <Label>Alternativas máximas cuando una hora no esté libre</Label>
            <Input
              className="mt-2"
              type="number"
              min={1}
              max={10}
              {...register("max_proposed_slots", { valueAsNumber: true })}
            />
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <SwitchField
            label="Responder directamente al consultar disponibilidad"
            description="Evita frases como «voy a comprobarlo» o «ya he revisado los huecos» y responde directamente con el resultado."
            checked={watch("direct_availability_response")}
            onChange={(checked) =>
              setValue("direct_availability_response", checked)
            }
          />
          <SwitchField
            label="Responder directamente al reservar"
            description="Evita «voy a reservarla» y confirma la cita solo cuando el calendario devuelve éxito."
            checked={watch("direct_booking_response")}
            onChange={(checked) => setValue("direct_booking_response", checked)}
          />
          <SwitchField
            label="Confirmar la fecha y hora completas al reservar"
            description="Ej.: «Queda reservada para el 26 de agosto a las doce de la mañana»."
            checked={watch("booking_confirmation_datetime_enabled")}
            onChange={(checked) =>
              setValue("booking_confirmation_datetime_enabled", checked)
            }
          />
          <SwitchField
            label="Preguntar si necesita algo más después de reservar"
            description="Si responde que sí, continúa ayudando y vuelve a preguntar al terminar."
            checked={watch("post_booking_followup_enabled")}
            onChange={(checked) =>
              setValue("post_booking_followup_enabled", checked)
            }
          />
          <SwitchField
            label="Colgar cuando confirme que no necesita nada más"
            description="Reproduce la despedida y finaliza la llamada automáticamente."
            checked={watch("hangup_after_no_more_help")}
            onChange={(checked) => setValue("hangup_after_no_more_help", checked)}
          />
          <SwitchField
            label="Colgar ante una despedida natural"
            description="Reconoce expresiones como «adiós», «chao», «hasta luego» o «gracias, nada más»."
            checked={watch("hangup_on_natural_goodbye")}
            onChange={(checked) => setValue("hangup_on_natural_goodbye", checked)}
          />
        </div>
        {watch("post_booking_followup_enabled") ? (
          <div className="mt-4">
            <Label>Pregunta después de reservar</Label>
            <Input
              {...register("post_booking_followup_message")}
              placeholder="¿Puedo ayudarte con algo más?"
            />
          </div>
        ) : null}
      </Section>

      <Section
        title="Conocimiento, transcripciones y privacidad"
        description="Información que puede utilizar el asistente y qué se conserva después de cada llamada."
      >
        <div className="grid gap-3 md:grid-cols-2">
          <SwitchField
            label="Usar la base de conocimiento"
            checked={useKnowledgeBase}
            onChange={(checked) => setValue("use_knowledge_base", checked)}
          />
          <SwitchField
            label="Guardar transcripciones"
            description="Permite leer la conversación desde el panel y la incluye en el JSON exportado."
            checked={transcriptEnabled}
            onChange={(checked) => setValue("transcript_enabled", checked)}
          />
        </div>
        {transcriptEnabled ? (
          <div className="mt-5 max-w-xs">
            <Label>Días de conservación</Label>
            <Input
              type="number"
              min={1}
              max={3650}
              {...register("conversation_retention_days", {
                valueAsNumber: true,
              })}
            />
          </div>
        ) : null}
      </Section>

      <Section
        title="Instrucciones de comportamiento"
        description="Añade únicamente reglas específicas de tu negocio. El prompt general ya está optimizado para sonar natural."
      >
        <div className="space-y-5">
          <div>
            <Label>Instrucciones adicionales</Label>
            <Textarea
              rows={4}
              {...register("additional_instructions")}
              placeholder="Ej.: si preguntan por aparcamiento, indicar que hay parking público enfrente."
            />
          </div>
          <div>
            <Label>Frases o expresiones que debe evitar</Label>
            <Textarea
              rows={3}
              {...register("forbidden_phrases")}
              placeholder="Una por línea"
            />
          </div>
          <details className="rounded-xl border border-[#e4e8ef] bg-white p-4">
            <summary className="cursor-pointer font-semibold text-[#27334a]">
              Mensajes especiales
            </summary>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <Label>Sin disponibilidad</Label>
                <Textarea rows={3} {...register("no_availability_message")} />
              </div>
              <div>
                <Label>Transferencia a persona</Label>
                <Textarea rows={3} {...register("human_transfer_message")} />
              </div>
              <div>
                <Label>Emergencia</Label>
                <Textarea rows={3} {...register("emergency_message")} />
              </div>
              <div>
                <Label>Despedida</Label>
                <Textarea rows={3} {...register("closing_message")} />
              </div>
            </div>
          </details>
        </div>
      </Section>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e4e8ef] pt-5">
        <label className="flex items-center gap-2 text-sm font-semibold text-[#27334a]">
          <input
            type="checkbox"
            className="size-5 accent-[#315efb]"
            {...register("is_active")}
          />
          Activar esta configuración al guardar
        </label>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancelar
          </Button>
          <Button type="submit" disabled={isPending}>
            <Save className="size-4" />
            {isPending ? "Guardando…" : "Guardar configuración"}
          </Button>
        </div>
      </div>

    </form>
  );
}
