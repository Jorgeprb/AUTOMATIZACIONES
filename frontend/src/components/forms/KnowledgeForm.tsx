import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  knowledgeCategoryLabels,
  knowledgeDefaults,
  knowledgeFormSchema,
  type KnowledgeFormValues,
} from "@/schemas/knowledge";

export function KnowledgeForm({
  defaultValues = knowledgeDefaults,
  onSubmit,
  onCancel,
  isPending,
}: {
  defaultValues?: KnowledgeFormValues;
  onSubmit: (values: KnowledgeFormValues) => void | Promise<unknown>;
  onCancel: () => void;
  isPending: boolean;
}) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<KnowledgeFormValues>({
    resolver: zodResolver(knowledgeFormSchema),
    defaultValues,
  });

  useEffect(() => reset(defaultValues), [defaultValues, reset]);

  return (
    <form className="space-y-4" onSubmit={handleSubmit(onSubmit)}>
      <div>
        <Label htmlFor="knowledge-title">Título</Label>
        <Input id="knowledge-title" className="mt-1.5" {...register("title")} />
        {errors.title ? (
          <p className="mt-1 text-xs text-[#bd3341]">{errors.title.message}</p>
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="knowledge-category">Categoría</Label>
          <Select
            id="knowledge-category"
            className="mt-1.5"
            {...register("category")}
          >
            {Object.entries(knowledgeCategoryLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="knowledge-priority">Prioridad</Label>
          <Input
            id="knowledge-priority"
            type="number"
            className="mt-1.5"
            {...register("priority", { valueAsNumber: true })}
          />
        </div>
      </div>
      <div>
        <Label htmlFor="knowledge-content">Contenido</Label>
        <Textarea
          id="knowledge-content"
          className="mt-1.5 min-h-52"
          placeholder="Información concreta que el asistente puede comunicar."
          {...register("content")}
        />
        {errors.content ? (
          <p className="mt-1 text-xs text-[#bd3341]">{errors.content.message}</p>
        ) : null}
      </div>
      <label className="flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
        <input
          type="checkbox"
          className="size-4 accent-[#315efb]"
          {...register("is_active")}
        />
        Incluir en el contexto activo
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending}>
          {isPending ? "Guardando…" : "Guardar contexto"}
        </Button>
      </div>
    </form>
  );
}
