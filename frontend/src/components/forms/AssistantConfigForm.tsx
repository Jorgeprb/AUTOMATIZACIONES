import { zodResolver } from "@hookform/resolvers/zod";
import { Bot, ShieldAlert, Sparkles, Volume2 } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

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

export function AssistantConfigForm({
  options,
  defaultValues = assistantConfigDefaults,
  onSubmit,
  onCancel,
  isPending,
}: {
  options: AssistantOptions;
  defaultValues?: AssistantConfigFormValues;
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

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

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
        </div>
        <p className="mt-2 text-xs text-[#6f7c92]">
          Cambia saludo y prompts. Conserva nombre, modelo, voz, estado,
          privacidad y retención.
        </p>
      </div>

      <FormSection
        title="Identidad"
        description="Nombre interno, idioma y saludo inicial."
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
        <div className="sm:col-span-2">
          <Label htmlFor="assistant-first-message">Primer mensaje</Label>
          <Textarea
            id="assistant-first-message"
            className="mt-1.5 min-h-24"
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

      <FormSection
        title="Voz y modelo"
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
            OpenAI no documenta una voz específica para castellano de España o
            gallego. El idioma se controla por prompt; Marin y Cedar son las
            voces recomendadas.
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
          <p className="mt-1 text-xs text-[#7d8899]">
            Se guarda como preferencia. El payload Realtime actual no la envía.
          </p>
        </div>
        <label className="mt-6 flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("is_active")}
          />
          Activar al guardar
        </label>
      </FormSection>

      <FormSection
        title="Reservas"
        description="Comportamiento general y reglas de agenda."
      >
        <div className="sm:col-span-2">
          <Label htmlFor="assistant-system-prompt">Prompt de sistema</Label>
          <Textarea
            id="assistant-system-prompt"
            className="mt-1.5 min-h-44"
            {...register("system_prompt")}
          />
          <FieldError message={errors.system_prompt?.message} />
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

      <FormSection
        title="Seguridad médica"
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
      </FormSection>

      <FormSection
        title="Transferencia"
        description="Cuándo debe pedir ayuda humana."
      >
        <div className="sm:col-span-2">
          <Textarea
            aria-label="Política de transferencia"
            className="min-h-36"
            {...register("transfer_policy_prompt")}
          />
          <FieldError message={errors.transfer_policy_prompt?.message} />
        </div>
      </FormSection>

      <FormSection
        title="Privacidad y retención"
        description="Preferencias aplicadas a nuevas llamadas."
      >
        <label className="flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("transcript_enabled")}
          />
          Guardar transcripción
        </label>
        <label className="flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("recording_enabled")}
          />
          Habilitar grabación
        </label>
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
        <div className="rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-3 text-xs leading-5 text-[#78591d]">
          La preferencia de grabación se persiste, pero este MVP todavía no
          captura ni almacena audio.
        </div>
      </FormSection>

      <div className="rounded-xl border bg-[#fbfcfe] p-4">
        <div className="flex items-center gap-2 font-semibold text-[#27334a]">
          <Bot className="size-4 text-[#315efb]" />
          Preview
        </div>
        <p className="mt-1 text-sm text-[#6f7c92]">
          Guarda la configuración para renderizar el prompt final con servicios,
          trabajadores, horarios y conocimiento actuales.
        </p>
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
