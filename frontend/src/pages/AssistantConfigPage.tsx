import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Clipboard,
  Eye,
  FileText,
  Pencil,
  Plus,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  activateAssistantConfig,
  createAssistantConfig,
  getAssistantOptions,
  listAssistantConfigs,
  previewPrompt,
  updateAssistantConfig,
} from "@/api/assistants";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { AssistantConfigForm } from "@/components/forms/AssistantConfigForm";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import {
  assistantConfigDefaults,
  type AssistantConfigFormValues,
  type AssistantConfigPayload,
} from "@/schemas/assistant";
import type { AssistantConfig, PromptPreview } from "@/schemas/domain";

function formValues(config: AssistantConfig): AssistantConfigFormValues {
  return {
    name: config.name,
    is_active: config.is_active,
    realtime_model: config.realtime_model,
    realtime_voice: config.realtime_voice,
    call_audio_mode: config.call_audio_mode,
    voice_provider: config.voice_provider,
    tts_model: config.tts_model ?? "",
    voice_id: config.voice_id ?? "",
    voice_locale: config.voice_locale ?? "es-ES",
    voice_gender: config.voice_gender ?? "",
    azure_speech_region: config.azure_speech_region ?? "",
    voice_style: config.voice_style ?? "",
    voice_speed: config.voice_speed ?? "1.00",
    voice_pitch: config.voice_pitch ?? "0",
    voice_stability: config.voice_stability ?? "",
    voice_similarity: config.voice_similarity ?? "",
    voice_temperature: config.voice_temperature ?? "",
    output_audio_format: config.output_audio_format,
    telephony_codec: config.telephony_codec,
    external_voice_legal_confirmed: config.external_voice_legal_confirmed,
    voice_instructions: config.voice_instructions ?? "",
    voice_preset: config.voice_preset ?? "",
    tts_preview_voice: config.tts_preview_voice ?? "",
    fallback_voice: config.fallback_voice ?? "",
    speech_speed: config.speech_speed,
    pause_style: config.pause_style,
    phone_reading_style: config.phone_reading_style,
    date_reading_style: config.date_reading_style,
    price_reading_style: config.price_reading_style,
    allow_interruptions: config.allow_interruptions,
    turn_end_silence_ms: String(config.turn_end_silence_ms ?? 350),
    idle_timeout_ms: config.idle_timeout_ms ? String(config.idle_timeout_ms) : "",
    ai_disclosure_enabled: config.ai_disclosure_enabled,
    ai_disclosure_message: config.ai_disclosure_message ?? "",
    preview_audio_format: config.preview_audio_format,
    language: config.language,
    temperature: config.temperature ?? "0.80",
    first_message: config.first_message,
    system_prompt: config.system_prompt,
    safety_prompt: config.safety_prompt,
    booking_policy_prompt: config.booking_policy_prompt,
    cancellation_policy_prompt: config.cancellation_policy_prompt,
    transfer_policy_prompt: config.transfer_policy_prompt,
    tone: config.tone,
    response_length: config.response_length,
    ask_patient_name: config.ask_patient_name,
    ask_patient_phone: config.ask_patient_phone,
    ask_general_reason: config.ask_general_reason,
    allow_booking_without_worker: config.allow_booking_without_worker,
    allow_bookings: config.allow_bookings,
    allow_price_answers: config.allow_price_answers,
    ask_service: config.ask_service,
    service_prompt_mode: config.service_prompt_mode ?? "ask_open",
    known_customer_name_enabled: config.known_customer_name_enabled ?? true,
    known_customer_greeting_enabled: config.known_customer_greeting_enabled ?? true,
    known_customer_greeting_template: config.known_customer_greeting_template ?? "Ola, {customer_name}. En que podo axudarche?",
    known_customer_explanation_template: config.known_customer_explanation_template ?? "Non te preocupes, non son vidente. Recoñecín o número porque estás na base de datos para ofrecerche unha atención máis personalizada.",
    remember_customer_after_booking: config.remember_customer_after_booking ?? true,
    suggest_preferred_worker_enabled: config.suggest_preferred_worker_enabled ?? true,
    ask_worker_preference_enabled: config.ask_worker_preference_enabled ?? true,
    slot_interval_minutes: config.slot_interval_minutes ?? 15,
    direct_availability_response: config.direct_availability_response ?? true,
    direct_booking_response: config.direct_booking_response ?? true,
    booking_confirmation_datetime_enabled:
      config.booking_confirmation_datetime_enabled ?? true,
    post_booking_followup_enabled: config.post_booking_followup_enabled ?? true,
    post_booking_followup_message:
      config.post_booking_followup_message ?? "¿Puedo ayudarte con algo más?",
    hangup_after_no_more_help: config.hangup_after_no_more_help ?? true,
    hangup_on_natural_goodbye: config.hangup_on_natural_goodbye ?? true,
    max_proposed_slots: config.max_proposed_slots,
    max_consecutive_questions: config.max_consecutive_questions,
    conversation_style: config.conversation_style,
    initiative_level: config.initiative_level,
    commercial_call_handling: config.commercial_call_handling,
    allow_cancellations: config.allow_cancellations,
    allow_reschedules: config.allow_reschedules,
    natural_confirmation_required: config.natural_confirmation_required,
    avoid_exact_confirmation_phrases: config.avoid_exact_confirmation_phrases,
    additional_instructions: config.additional_instructions ?? "",
    forbidden_phrases: config.forbidden_phrases ?? "",
    no_availability_message: config.no_availability_message ?? "",
    missing_calendar_message: config.missing_calendar_message ?? "",
    emergency_message: config.emergency_message ?? "",
    human_transfer_message: config.human_transfer_message ?? "",
    human_transfer_rules: config.human_transfer_rules ?? "",
    commercial_call_message: config.commercial_call_message ?? "",
    conversation_extra_rules: config.conversation_extra_rules ?? "",
    closing_message: config.closing_message ?? "",
    use_prices: config.use_prices,
    use_knowledge_base: config.use_knowledge_base,
    strict_calendar_mode: config.strict_calendar_mode,
    transcript_enabled: config.transcript_enabled,
    recording_enabled: config.recording_enabled,
    conversation_retention_days: config.conversation_retention_days,
  };
}

function speechSpeedForMultiplier(value: string): "slow" | "normal" | "fast" {
  const multiplier = Number(value);
  if (multiplier < 0.9) return "slow";
  if (multiplier > 1.15) return "fast";
  return "normal";
}

function payload(
  values: AssistantConfigFormValues,
  isActive: boolean,
): AssistantConfigPayload {
  const externalVoice = values.voice_provider !== "openai";
  return {
    ...values,
    is_active: isActive,
    call_audio_mode: externalVoice ? "vps_media_bridge" : values.call_audio_mode,
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

export function AssistantConfigPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<AssistantConfig | null>(null);

  const query = useQuery({
    queryKey: ["assistants", clinicId],
    queryFn: () => listAssistantConfigs(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const optionsQuery = useQuery({
    queryKey: ["assistant-options"],
    queryFn: getAssistantOptions,
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["assistants", clinicId] });
  };
  const saveMutation = useMutation({
    mutationFn: async (values: AssistantConfigFormValues) => {
      const shouldActivate = values.is_active;
      let saved: AssistantConfig;
      if (editingConfig) {
        const updatePayload = payload(values, false);
        if (shouldActivate) {
          delete (updatePayload as Partial<AssistantConfigPayload>).is_active;
        }
        saved = await updateAssistantConfig(
          clinicId as string,
          editingConfig.id,
          updatePayload,
        );
      } else {
        saved = await createAssistantConfig(
          clinicId as string,
          payload(values, false),
        );
      }
      return shouldActivate
        ? activateAssistantConfig(clinicId as string, saved.id)
        : saved;
    },
    onSuccess: async () => {
      await refresh();
      setEditingConfig(null);
      setFormOpen(false);
      toast.success("Configuración guardada");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const activateMutation = useMutation({
    mutationFn: (configId: string) =>
      activateAssistantConfig(clinicId as string, configId),
    onSuccess: async () => {
      await refresh();
      toast.success("Configuración activada");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const previewMutation = useMutation({
    mutationFn: (configId: string) =>
      previewPrompt(clinicId as string, configId),
    onSuccess: setPreview,
    onError: (error: Error) => toast.error(error.message),
  });

  const options = optionsQuery.data;
  const newDefaults: AssistantConfigFormValues = options
    ? {
        ...assistantConfigDefaults,
        realtime_model: options.default_model,
        realtime_voice: options.default_voice,
      }
    : assistantConfigDefaults;

  return (
    <div className="space-y-7">
      <PageHeader
        title="Configuración del asistente"
        description="Configura cómo habla, escucha y actúa el asistente, sin exponer detalles técnicos internos."
        actions={
          <Button
            disabled={!options}
            onClick={() => {
              setEditingConfig(null);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            Nueva configuración
          </Button>
        }
      />

      {query.isLoading || optionsQuery.isLoading ? <LoadingState rows={4} /> : null}
      {query.error ? <ErrorState error={query.error} /> : null}
      {optionsQuery.error ? <ErrorState error={optionsQuery.error} /> : null}

      {query.data?.items.length ? (
        <div className="grid gap-5 xl:grid-cols-2">
          {query.data.items.map((config) => (
            <Card key={config.id}>
              <CardHeader className="flex-row items-start justify-between">
                <div>
                  <CardTitle>{config.name}</CardTitle>
                  <CardDescription>
                    {config.language} · {config.tone} · {config.response_length} · retención {config.conversation_retention_days} días
                  </CardDescription>
                </div>
                <StatusBadge status={config.is_active ? "success" : "neutral"}>
                  {config.is_active ? "Activa" : "Inactiva"}
                </StatusBadge>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-[#f7f9fc] p-3">
                    <div className="text-xs font-semibold text-[#7a8598]">Voz</div>
                    <p className="mt-2 truncate text-sm font-semibold text-[#27334a]">
                      {config.voice_id || config.realtime_voice}
                    </p>
                  </div>
                  <div className="rounded-xl bg-[#f7f9fc] p-3">
                    <div className="text-xs font-semibold text-[#7a8598]">Conversación</div>
                    <p className="mt-2 text-sm font-semibold text-[#27334a]">
                      {config.tone} · {config.allow_interruptions ? "interrumpible" : "sin interrupciones"}
                    </p>
                  </div>
                </div>
                <div className="rounded-xl border p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[#8490a2]">
                    Primer mensaje
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#526078]">
                    {config.first_message}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge
                    status={config.transcript_enabled ? "info" : "neutral"}
                  >
                    {`Transcripción ${
                      config.transcript_enabled ? "activa" : "desactivada"
                    }`}
                  </StatusBadge>
                  <StatusBadge status="neutral">
                    {`Idioma: ${config.language}`}
                  </StatusBadge>
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditingConfig(config);
                      setFormOpen(true);
                    }}
                  >
                    <Pencil className="size-4" />
                    Editar
                  </Button>
                  <Button
                    variant="outline"
                    disabled={previewMutation.isPending}
                    onClick={() => previewMutation.mutate(config.id)}
                  >
                    <Eye className="size-4" />
                    Revisar comportamiento
                  </Button>
                  <Button
                    variant={config.is_active ? "secondary" : "default"}
                    disabled={config.is_active || activateMutation.isPending}
                    onClick={() => activateMutation.mutate(config.id)}
                  >
                    <CheckCircle2 className="size-4" />
                    {config.is_active ? "Activa" : "Activar"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !query.isLoading && !query.error ? (
        <EmptyState
          icon={Bot}
          title="Sin configuración"
          description="Crea la primera configuración del asistente."
          action={
            <Button onClick={() => setFormOpen(true)} disabled={!options}>
              <Plus className="size-4" />
              Crear configuración
            </Button>
          }
        />
      ) : null}

      <Dialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingConfig(null);
        }}
      >
        <DialogContent className="max-h-[92vh] max-w-6xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingConfig ? "Editar configuración" : "Nueva configuración"}
            </DialogTitle>
            <DialogDescription>
              Configura únicamente cómo debe hablar, escuchar y actuar el asistente.
            </DialogDescription>
          </DialogHeader>
          {options ? (
            <AssistantConfigForm
              clinicId={clinicId as string}
              assistantConfigId={editingConfig?.id ?? null}
              options={options}
              defaultValues={
                editingConfig ? formValues(editingConfig) : newDefaults
              }
              onSubmit={(values) => saveMutation.mutateAsync(values)}
              onCancel={() => setFormOpen(false)}
              isPending={saveMutation.isPending}
            />
          ) : (
            <LoadingState rows={5} />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="size-5 text-[#315efb]" />
              Comportamiento completo del asistente
            </DialogTitle>
            <DialogDescription>
              Reglas e información que utilizará durante las llamadas.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end">
            <Button
              variant="outline"
              onClick={async () => {
                if (!preview) return;
                await navigator.clipboard.writeText(preview.prompt);
                toast.success("Prompt copiado");
              }}
            >
              <Clipboard className="size-4" />
              Copiar comportamiento
            </Button>
          </div>
          <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-xl bg-[#111827] p-5 text-xs leading-6 text-[#e5e7eb]">
            {preview?.prompt}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
