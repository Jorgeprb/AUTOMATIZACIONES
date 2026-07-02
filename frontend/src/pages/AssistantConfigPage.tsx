import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clipboard,
  Eye,
  FileText,
  Mic2,
  Pencil,
  Plus,
  Sparkles,
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
import { getPromptContextPreview } from "@/api/knowledge";
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
    language: config.language,
    temperature: config.temperature ?? "",
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

function payload(
  values: AssistantConfigFormValues,
  isActive: boolean,
): AssistantConfigPayload {
  return {
    ...values,
    is_active: isActive,
    temperature: values.temperature || null,
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
  const contextQuery = useQuery({
    queryKey: ["prompt-context-preview", clinicId],
    queryFn: () => getPromptContextPreview(clinicId as string),
    enabled: Boolean(clinicId),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["assistants", clinicId] });
    await queryClient.invalidateQueries({
      queryKey: ["prompt-context-preview", clinicId],
    });
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
        description="Define identidad, voz, políticas, privacidad y comportamiento por clínica."
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

      {contextQuery.data?.warnings.length ? (
        <div className="grid gap-2 md:grid-cols-2">
          {contextQuery.data.warnings
            .filter((warning) =>
              [
                "No hay servicios activos.",
                "No hay trabajadores activos.",
                "No hay calendario conectado.",
                "No hay número configurado.",
              ].includes(warning),
            )
            .map((warning) => (
              <div
                key={warning}
                className="flex items-start gap-2 rounded-xl border border-[#ffe0a5] bg-[#fff9ec] px-4 py-3 text-sm text-[#78591d]"
              >
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                {warning}
              </div>
            ))}
        </div>
      ) : null}

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
                    <div className="flex items-center gap-2 text-xs font-semibold text-[#7a8598]">
                      <Sparkles className="size-3.5" /> Modelo
                    </div>
                    <p className="mt-2 truncate text-sm font-semibold text-[#27334a]">
                      {config.realtime_model}
                    </p>
                  </div>
                  <div className="rounded-xl bg-[#f7f9fc] p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-[#7a8598]">
                      <Mic2 className="size-3.5" /> Voz
                    </div>
                    <p className="mt-2 text-sm font-semibold text-[#27334a]">
                      {config.realtime_voice}
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
                  <StatusBadge
                    status={config.recording_enabled ? "warning" : "neutral"}
                  >
                    {`Grabación ${
                      config.recording_enabled ? "solicitada" : "desactivada"
                    }`}
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
                    Previsualizar prompt final
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
              Los prompts avanzados quedan visibles y agrupados por función.
            </DialogDescription>
          </DialogHeader>
          {options ? (
            <AssistantConfigForm
              clinicId={clinicId as string}
              options={options}
              defaultValues={
                editingConfig ? formValues(editingConfig) : newDefaults
              }
              contextWarnings={contextQuery.data?.warnings ?? []}
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
              Prompt renderizado
            </DialogTitle>
            <DialogDescription>
              {preview
                ? `${preview.realtime_model} · ${preview.realtime_voice} · ${preview.language}`
                : ""}
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
              Copiar prompt
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
