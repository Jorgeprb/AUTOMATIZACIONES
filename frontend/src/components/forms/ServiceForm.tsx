import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { FormSection } from "@/components/common/FormSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Worker } from "@/schemas/domain";
import {
  serviceDefaults,
  serviceFormSchema,
  type ServiceFormValues,
} from "@/schemas/service";

function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-medium text-[#bd3341]">{message}</p>
  ) : null;
}

export function ServiceForm({
  workers,
  defaultValues = serviceDefaults,
  onSubmit,
  onCancel,
  isPending,
}: {
  workers: Worker[];
  defaultValues?: ServiceFormValues;
  onSubmit: (values: ServiceFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<ServiceFormValues>({
    resolver: zodResolver(serviceFormSchema),
    defaultValues,
  });
  const requiresWorker = watch("requires_worker");

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  return (
    <form className="space-y-6" onSubmit={handleSubmit(onSubmit)}>
      <FormSection title="Identidad" description="Nombre interno y texto público.">
        <div>
          <Label htmlFor="service-name">Nombre interno</Label>
          <Input id="service-name" className="mt-1.5" {...register("name")} />
          <FieldError message={errors.name?.message} />
        </div>
        <div>
          <Label htmlFor="service-public-name">Nombre público</Label>
          <Input
            id="service-public-name"
            className="mt-1.5"
            {...register("public_name")}
          />
          <FieldError message={errors.public_name?.message} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="service-description">Descripción</Label>
          <Textarea
            id="service-description"
            className="mt-1.5"
            {...register("description")}
          />
        </div>
      </FormSection>

      <FormSection
        title="Comprensión por voz"
        description="Ayuda al asistente a clasificar expresiones libres sin inventar servicios."
      >
        <div>
          <Label htmlFor="service-aliases">Alias y sinónimos</Label>
          <Textarea id="service-aliases" className="mt-1.5" placeholder="corte de caballero, cortar el pelo" {...register("aliases_text")} />
        </div>
        <div>
          <Label htmlFor="service-keywords">Palabras clave</Label>
          <Textarea id="service-keywords" className="mt-1.5" placeholder="corte, pelo, caballero" {...register("keywords_text")} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="service-phrases">Expresiones habituales</Label>
          <Textarea id="service-phrases" className="mt-1.5" placeholder="Quiero cortarme el pelo\nSolo necesito un corte" {...register("common_phrases_text")} />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="service-disambiguation">Instrucciones de desambiguación</Label>
          <Textarea id="service-disambiguation" className="mt-1.5" placeholder="Diferenciar de corte y barba preguntando si también quiere arreglar la barba." {...register("disambiguation_instructions")} />
        </div>
      </FormSection>

      <FormSection
        title="Precio"
        description="El texto tiene prioridad al informar por teléfono."
      >
        <div>
          <Label htmlFor="service-price-text">Precio en texto</Label>
          <Input
            id="service-price-text"
            className="mt-1.5"
            placeholder="Desde 50 € / Consultar"
            {...register("price_text")}
          />
        </div>
        <div>
          <Label htmlFor="service-price-amount">Precio numérico opcional</Label>
          <Input
            id="service-price-amount"
            type="number"
            min="0"
            step="0.01"
            className="mt-1.5"
            {...register("price_amount")}
          />
          <FieldError message={errors.price_amount?.message} />
        </div>
        <div>
          <Label htmlFor="service-currency">Moneda</Label>
          <Input
            id="service-currency"
            className="mt-1.5 uppercase"
            {...register("currency")}
          />
          <FieldError message={errors.currency?.message} />
        </div>
      </FormSection>

      <FormSection title="Duración" description="Tiempo clínico y márgenes.">
        <div>
          <Label htmlFor="service-duration">Duración (minutos)</Label>
          <Input
            id="service-duration"
            type="number"
            min="1"
            className="mt-1.5"
            {...register("duration_minutes", { valueAsNumber: true })}
          />
          <FieldError message={errors.duration_minutes?.message} />
        </div>
        <div>
          <Label htmlFor="service-buffer-before">Buffer antes</Label>
          <Input
            id="service-buffer-before"
            type="number"
            min="0"
            className="mt-1.5"
            {...register("buffer_before_minutes", { valueAsNumber: true })}
          />
        </div>
        <div>
          <Label htmlFor="service-buffer-after">Buffer después</Label>
          <Input
            id="service-buffer-after"
            type="number"
            min="0"
            className="mt-1.5"
            {...register("buffer_after_minutes", { valueAsNumber: true })}
          />
        </div>
      </FormSection>

      <FormSection
        title="Asignación"
        description="Restringe qué trabajadores pueden prestar este servicio."
      >
        <label className="flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("requires_worker")}
          />
          Requiere trabajador
        </label>
        {requiresWorker ? (
          <div className="sm:col-span-2">
            <p className="mb-2 text-sm font-medium text-[#37445b]">
              Trabajadores permitidos
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {workers.map((worker) => (
                <label
                  key={worker.id}
                  className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm"
                >
                  <input
                    type="checkbox"
                    value={worker.id}
                    className="size-4 accent-[#315efb]"
                    {...register("allowed_worker_ids")}
                  />
                  {worker.name}
                </label>
              ))}
            </div>
            <p className="mt-2 text-xs text-[#7d8899]">
              Si no marcas ninguno, podrá atenderlo cualquier trabajador activo.
            </p>
          </div>
        ) : null}
      </FormSection>

      <FormSection title="Disponibilidad" description="Uso por el agente y estado.">
        <label className="flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("is_bookable_by_bot")}
          />
          Reservable por el bot
        </label>
        <label className="flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[#315efb]"
            {...register("is_active")}
          />
          Servicio activo
        </label>
      </FormSection>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Guardando…" : "Guardar servicio"}
        </Button>
      </div>
    </form>
  );
}
