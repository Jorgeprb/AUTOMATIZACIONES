import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";

import { FormSection } from "@/components/common/FormSection";
import { WeeklyHoursEditor } from "@/components/forms/WeeklyHoursEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  clinicDefaults,
  clinicFormSchema,
  type ClinicFormValues,
} from "@/schemas/clinic";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

export function ClinicForm({
  defaultValues = clinicDefaults,
  onSubmit,
  onCancel,
  isPending,
  submitLabel,
  hidePhoneNumber = false,
}: {
  defaultValues?: ClinicFormValues;
  onSubmit: (values: ClinicFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
  submitLabel: string;
  hidePhoneNumber?: boolean;
}) {
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ClinicFormValues>({
    resolver: zodResolver(clinicFormSchema),
    defaultValues,
  });

  useEffect(() => {
    reset(defaultValues);
  }, [defaultValues, reset]);

  return (
    <form className="space-y-6" onSubmit={handleSubmit(onSubmit)}>
      <FormSection
        title="Identidad"
        description="Datos visibles y legales de la clínica."
      >
        <div>
          <Label htmlFor="name">Nombre comercial</Label>
          <Input id="name" className="mt-1.5" {...register("name")} />
          <FieldError message={errors.name?.message} />
        </div>
        <div>
          <Label htmlFor="legal_name">Razón social</Label>
          <Input
            id="legal_name"
            className="mt-1.5"
            {...register("legal_name")}
          />
          <FieldError message={errors.legal_name?.message} />
        </div>
        {!hidePhoneNumber ? (
          <div>
            <Label htmlFor="main_phone_number">Teléfono principal</Label>
            <Input
              id="main_phone_number"
              className="mt-1.5"
              placeholder="+34910000000"
              {...register("main_phone_number")}
            />
            <FieldError message={errors.main_phone_number?.message} />
          </div>
        ) : null}
        <div>
          <Label htmlFor="email">Email público</Label>
          <Input
            id="email"
            type="email"
            className="mt-1.5"
            {...register("email")}
          />
          <FieldError message={errors.email?.message} />
        </div>
      </FormSection>

      <FormSection
        title="Localización"
        description="Zona horaria e información de contacto."
      >
        <div>
          <Label htmlFor="timezone">Zona horaria</Label>
          <Input id="timezone" className="mt-1.5" {...register("timezone")} />
          <FieldError message={errors.timezone?.message} />
        </div>
        <div>
          <Label htmlFor="default_language">Idioma</Label>
          <Input
            id="default_language"
            className="mt-1.5"
            {...register("default_language")}
          />
          <FieldError message={errors.default_language?.message} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="address">Dirección</Label>
          <Input id="address" className="mt-1.5" {...register("address")} />
          <FieldError message={errors.address?.message} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="website">Sitio web</Label>
          <Input
            id="website"
            className="mt-1.5"
            placeholder="https://..."
            {...register("website")}
          />
          <FieldError message={errors.website?.message} />
        </div>
      </FormSection>

      <FormSection
        title="Asistente"
        description="Contexto general y mensaje de seguridad."
      >
        <div className="sm:col-span-2">
          <Label htmlFor="description">Descripción pública</Label>
          <Textarea
            id="description"
            className="mt-1.5"
            {...register("description")}
          />
          <FieldError message={errors.description?.message} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="emergency_message">Mensaje de urgencias</Label>
          <Textarea
            id="emergency_message"
            className="mt-1.5"
            {...register("emergency_message")}
          />
          <FieldError message={errors.emergency_message?.message} />
        </div>
      </FormSection>

      <FormSection
        title="Horario general"
        description="Horario público habitual de la clínica."
      >
        <div className="sm:col-span-2">
          <Controller
            name="opening_hours_json"
            control={control}
            render={({ field }) => (
              <WeeklyHoursEditor value={field.value} onChange={field.onChange} />
            )}
          />
        </div>
      </FormSection>

      <FormSection
        title="Datos y estado"
        description="Retención mínima y disponibilidad de la clínica."
      >
        <div>
          <Label htmlFor="data_retention_days">Retención de llamadas (días)</Label>
          <Input
            id="data_retention_days"
            type="number"
            className="mt-1.5"
            {...register("data_retention_days", { valueAsNumber: true })}
          />
          <FieldError message={errors.data_retention_days?.message} />
        </div>
        <label className="mt-6 flex h-10 items-center gap-3 rounded-lg border border-[#dfe4ec] px-3 text-sm font-medium text-[#37445b]">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("is_active")}
          />
          Clínica activa
        </label>
      </FormSection>

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
