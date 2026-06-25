import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Eye, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  createKnowledge,
  deleteKnowledge,
  listKnowledge,
  updateKnowledge,
} from "@/api/knowledge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { PromptContextPreview } from "@/components/common/PromptContextPreview";
import { StatusBadge } from "@/components/common/StatusBadge";
import { KnowledgeForm } from "@/components/forms/KnowledgeForm";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import type { KnowledgeCategory, KnowledgeItem } from "@/schemas/domain";
import {
  knowledgeCategoryLabels,
  knowledgeDefaults,
  type KnowledgeFormValues,
} from "@/schemas/knowledge";

type CategoryFilter = "all" | KnowledgeCategory;

function formValues(item: KnowledgeItem): KnowledgeFormValues {
  return {
    title: item.title,
    category: item.category,
    content: item.content,
    priority: item.priority,
    is_active: item.is_active,
  };
}

export function KnowledgePage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<KnowledgeItem | null>(null);
  const [previewItem, setPreviewItem] = useState<KnowledgeItem | null>(null);
  const [deletingItem, setDeletingItem] = useState<KnowledgeItem | null>(null);

  const query = useQuery({
    queryKey: ["knowledge", clinicId, search, category],
    queryFn: () =>
      listKnowledge(clinicId as string, {
        q: search.trim() || undefined,
        category: category === "all" ? undefined : category,
      }),
    enabled: Boolean(clinicId),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["knowledge", clinicId] });
    await queryClient.invalidateQueries({
      queryKey: ["prompt-context-preview", clinicId],
    });
  };
  const createMutation = useMutation({
    mutationFn: (values: KnowledgeFormValues) =>
      createKnowledge(clinicId as string, values),
    onSuccess: async () => {
      await refresh();
      setFormOpen(false);
      toast.success("Contexto creado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const updateMutation = useMutation({
    mutationFn: ({
      itemId,
      values,
    }: {
      itemId: string;
      values: Partial<KnowledgeFormValues>;
    }) => updateKnowledge(clinicId as string, itemId, values),
    onSuccess: async () => {
      await refresh();
      setEditingItem(null);
      setFormOpen(false);
      toast.success("Contexto actualizado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (itemId: string) =>
      deleteKnowledge(clinicId as string, itemId),
    onSuccess: async () => {
      await refresh();
      setDeletingItem(null);
      toast.success("Contexto eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const columns = useMemo<Array<DataTableColumn<KnowledgeItem>>>(
    () => [
      {
        key: "title",
        header: "Elemento",
        cell: (item) => (
          <div>
            <p className="font-semibold text-[#27334a]">{item.title}</p>
            <p className="mt-1 max-w-xl truncate text-xs text-[#7b8799]">
              {item.content}
            </p>
          </div>
        ),
      },
      {
        key: "category",
        header: "Categoría",
        cell: (item) => (
          <StatusBadge status="info">
            {knowledgeCategoryLabels[item.category]}
          </StatusBadge>
        ),
      },
      {
        key: "priority",
        header: "Prioridad",
        cell: (item) => item.priority,
      },
      {
        key: "status",
        header: "Estado",
        cell: (item) => (
          <StatusBadge status={item.is_active ? "success" : "neutral"}>
            {item.is_active ? "Activo" : "Inactivo"}
          </StatusBadge>
        ),
      },
      {
        key: "actions",
        header: "",
        className: "w-[170px]",
        cell: (item) => (
          <div className="flex justify-end">
            <Button
              size="icon"
              variant="ghost"
              title="Previsualizar"
              onClick={() => setPreviewItem(item)}
            >
              <Eye className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title={item.is_active ? "Desactivar" : "Activar"}
              onClick={() =>
                updateMutation.mutate({
                  itemId: item.id,
                  values: { is_active: !item.is_active },
                })
              }
            >
              <Power
                className={`size-4 ${item.is_active ? "text-[#b46a13]" : "text-[#24804a]"}`}
              />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title="Editar"
              onClick={() => {
                setEditingItem(item);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title="Eliminar"
              onClick={() => setDeletingItem(item)}
            >
              <Trash2 className="size-4 text-[#bd3341]" />
            </Button>
          </div>
        ),
      },
    ],
    [updateMutation],
  );

  return (
    <div className="space-y-7">
      <PageHeader
        title="Conocimiento"
        description="Precios, normas, FAQs y contexto práctico que puede comunicar el asistente."
        actions={
          <Button
            onClick={() => {
              setEditingItem(null);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            Añadir contexto
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-[1fr_220px]">
        <Input
          aria-label="Buscar conocimiento"
          placeholder="Buscar por título o contenido…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Select
          aria-label="Filtrar por categoría"
          value={category}
          onChange={(event) =>
            setCategory(event.target.value as CategoryFilter)
          }
        >
          <option value="all">Todas las categorías</option>
          {Object.entries(knowledgeCategoryLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {query.isLoading ? <LoadingState rows={6} /> : null}
      {query.error ? <ErrorState error={query.error} /> : null}
      {query.data?.items.length ? (
        <DataTable columns={columns} rows={query.data.items} rowKey={(row) => row.id} />
      ) : !query.isLoading && !query.error ? (
        <EmptyState
          icon={BookOpen}
          title="No hay contexto cargado para el asistente"
          description="Añade precios, preguntas frecuentes, ubicación, seguros o políticas."
          action={
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="size-4" />
              Añadir contexto
            </Button>
          }
        />
      ) : null}

      {clinicId ? <PromptContextPreview clinicId={clinicId} /> : null}

      <Dialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingItem(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingItem ? "Editar contexto" : "Nuevo contexto"}
            </DialogTitle>
            <DialogDescription>
              Solo los elementos activos se incluirán en el prompt.
            </DialogDescription>
          </DialogHeader>
          <KnowledgeForm
            defaultValues={editingItem ? formValues(editingItem) : knowledgeDefaults}
            onSubmit={(values) =>
              editingItem
                ? updateMutation.mutateAsync({
                    itemId: editingItem.id,
                    values,
                  })
                : createMutation.mutateAsync(values)
            }
            onCancel={() => setFormOpen(false)}
            isPending={createMutation.isPending || updateMutation.isPending}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(previewItem)} onOpenChange={() => setPreviewItem(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Vista previa en el prompt</DialogTitle>
            <DialogDescription>
              Este bloque solo entrará si el elemento está activo.
            </DialogDescription>
          </DialogHeader>
          <pre className="whitespace-pre-wrap rounded-xl bg-[#111827] p-5 text-sm leading-6 text-[#e5e7eb]">
            {previewItem
              ? `- [${previewItem.category}] ${previewItem.title}: ${previewItem.content}`
              : ""}
          </pre>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deletingItem)}
        onOpenChange={(open) => {
          if (!open) setDeletingItem(null);
        }}
        title="Eliminar contexto"
        description={`Se eliminará ${deletingItem?.title ?? "este elemento"}.`}
        confirmLabel="Eliminar"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deletingItem) deleteMutation.mutate(deletingItem.id);
        }}
      />
    </div>
  );
}
