import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";

import { FormSection } from "@/components/common/FormSection";
import { WeeklyHoursSummary } from "@/components/common/WeeklyHoursSummary";
import { WeeklyHoursEditor } from "@/components/forms/WeeklyHoursEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { WeeklyHours } from "@/schemas/hours";
import {
  workerDefaults,
  workerFormSchema,
  type WorkerFormValues,
} from "@/schemas/worker";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

export function WorkerForm({
  defaultValues = workerDefaults,
  clinicHours,
  onSubmit,
  onCancel,
  isPending,
  submitLabel,
}: {
  defaultValues?: WorkerFormValues;
  clinicHours: WeeklyHours;
  onSubmit: (values: WorkerFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
  submitLabel: string;
}) {
  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<WorkerFormValues>({
    resolver: zodResolver(workerFormSchema),
    defaultValues,
  });
  const inheritsClinicHours = watch("inherit_clinic_hours");

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  return (
    <form className="space-y-6" onSubmit={handleSubmit(onSubmit)}>
      <FormSection title="Perfil" description="Datos públicos del trabajador.">
        <div>
          <Label htmlFor="worker-name">Nombre</Label>
          <Input id="worker-name" className="mt-1.5" {...register("name")} />
          <FieldError message={errors.name?.message} />
        </div>
        <div>
          <Label htmlFor="worker-role">Rol</Label>
          <Input id="worker-role" className="mt-1.5" {...register("role")} />
          <FieldError message={errors.role?.message} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="worker-description">Descripción pública</Label>
          <Textarea
            id="worker-description"
            className="mt-1.5"
            {...register("public_description")}
          />
        </div>
        <div>
          <Label htmlFor="worker-email">Email</Label>
          <Input
            id="worker-email"
            type="email"
            className="mt-1.5"
            {...register("email")}
          />
          <FieldError message={errors.email?.message} />
        </div>
        <div>
          <Label htmlFor="worker-extension">Extensión telefónica</Label>
          <Input
            id="worker-extension"
            className="mt-1.5"
            {...register("phone_extension")}
          />
        </div>
      </FormSection>

      <FormSection
        title="Calendario"
        description="La vinculación con Google Calendar se gestiona desde Integración de calendario."
      >
        <div>
          <Label htmlFor="worker-calendar">Calendar ID</Label>
          <Input
            id="worker-calendar"
            className="mt-1.5"
            {...register("calendar_id")}
          />
        </div>
        <div>
          <Label htmlFor="worker-color">Color del evento</Label>
          <Input
            id="worker-color"
            className="mt-1.5"
            {...register("color_id")}
          />
        </div>
      </FormSection>

      <FormSection
        title="Horario laboral"
        description="El horario efectivo se usa para calcular la disponibilidad real del trabajador."
      >
        <div className="sm:col-span-2 space-y-4">
          <label className="flex items-start gap-3 rounded-xl border border-[#dce4f4] bg-[#f7f9ff] p-4 text-sm text-[#354158]">
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-[#315efb]"
              {...register("inherit_clinic_hours")}
            />
            <span>
              <strong className="block">Heredar el horario de la clínica</strong>
              <span className="mt-1 block text-xs leading-5 text-[#6e7a90]">
                Si está marcado, cualquier cambio en el horario general de la clínica se aplicará automáticamente a este trabajador. Si lo desmarcas, se utilizará exclusivamente su horario personalizado.
              </span>
            </span>
          </label>

          {inheritsClinicHours ? (
            <div className="rounded-xl border border-[#e5e9f0] bg-[#fafbfe] p-4">
              <div className="mb-3 flex items-start gap-2 text-sm text-[#5e6b80]">
                <Info className="mt-0.5 size-4 shrink-0 text-[#315efb]" />
                Horario heredado actualmente de la clínica.
              </div>
              <WeeklyHoursSummary value={clinicHours} compact />
            </div>
          ) : (
            <Controller
              name="working_hours_json"
              control={control}
              render={({ field }) => (
                <WeeklyHoursEditor value={field.value} onChange={field.onChange} />
              )}
            />
          )}
        </div>
      </FormSection>

      <label className="flex h-10 items-center gap-3 rounded-lg border border-[#dfe4ec] px-3 text-sm font-medium text-[#37445b]">
        <input
          type="checkbox"
          className="size-4 accent-[#315efb]"
          {...register("is_active")}
        />
        Trabajador activo
      </label>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Guardando…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
