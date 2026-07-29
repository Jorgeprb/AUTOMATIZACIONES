import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Eye,
  FileText,
  Link as LinkIcon,
  Pencil,
  Plus,
  Power,
  Trash2,
  Upload,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  createKnowledge,
  deleteKnowledge,
  importPdfKnowledge,
  importUrlKnowledge,
  listKnowledge,
  previewPdfKnowledge,
  previewUrlKnowledge,
  updateKnowledge,
} from "@/api/knowledge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
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
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import type {
  KnowledgeCategory,
  KnowledgeImportPreview,
  KnowledgeItem,
} from "@/schemas/domain";
import {
  knowledgeCategoryLabels,
  knowledgeDefaults,
  type KnowledgeFormValues,
} from "@/schemas/knowledge";

type CategoryFilter = "all" | KnowledgeCategory;
type ImportMode = "pdf" | "url";

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
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<ImportMode>("pdf");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importUrl, setImportUrl] = useState("");
  const [importTitle, setImportTitle] = useState("");
  const [importCategory, setImportCategory] = useState<KnowledgeCategory>("faq");
  const [importPriority, setImportPriority] = useState(0);
  const [importActive, setImportActive] = useState(true);
  const [importPreview, setImportPreview] =
    useState<KnowledgeImportPreview | null>(null);
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
  const previewImportMutation = useMutation({
    mutationFn: () => {
      if (importMode === "pdf") {
        if (!importFile) throw new Error("Selecciona un PDF.");
        return previewPdfKnowledge(clinicId as string, {
          file: importFile,
          category: importCategory,
        });
      }
      return previewUrlKnowledge(clinicId as string, {
        url: importUrl,
        title: importTitle || undefined,
        category: importCategory,
        priority: importPriority,
        is_active: importActive,
      });
    },
    onSuccess: (data) => {
      setImportPreview(data);
      if (!importTitle) setImportTitle(data.title);
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const saveImportMutation = useMutation({
    mutationFn: () => {
      if (importMode === "pdf") {
        if (!importFile) throw new Error("Selecciona un PDF.");
        return importPdfKnowledge(clinicId as string, {
          file: importFile,
          title: importTitle || importPreview?.title,
          category: importCategory,
          priority: importPriority,
          is_active: importActive,
        });
      }
      return importUrlKnowledge(clinicId as string, {
        url: importUrl,
        title: importTitle || importPreview?.title,
        category: importCategory,
        priority: importPriority,
        is_active: importActive,
      });
    },
    onSuccess: async () => {
      await refresh();
      setImportOpen(false);
      setImportPreview(null);
      setImportFile(null);
      setImportUrl("");
      setImportTitle("");
      toast.success("Contexto importado");
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
            {item.source_type !== "manual" ? (
              <p className="mt-1 max-w-xl truncate text-xs text-[#315efb]">
                {item.source_type.toUpperCase()} · {item.source}
              </p>
            ) : null}
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
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setImportOpen(true);
                setImportPreview(null);
              }}
            >
              <Upload className="size-4" />
              Importar PDF/URL
            </Button>
            <Button
              onClick={() => {
                setEditingItem(null);
                setFormOpen(true);
              }}
            >
              <Plus className="size-4" />
              Añadir texto manual
            </Button>
          </div>
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

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          setImportOpen(open);
          if (!open) setImportPreview(null);
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Importar conocimiento</DialogTitle>
            <DialogDescription>
              Previsualiza el texto extraído antes de guardarlo en el prompt.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="knowledge-import-mode">Origen</Label>
              <Select
                id="knowledge-import-mode"
                className="mt-1.5"
                value={importMode}
                onChange={(event) => {
                  setImportMode(event.target.value as ImportMode);
                  setImportPreview(null);
                }}
              >
                <option value="pdf">PDF subido</option>
                <option value="url">URL de página web</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="knowledge-import-category">Categoría</Label>
              <Select
                id="knowledge-import-category"
                className="mt-1.5"
                value={importCategory}
                onChange={(event) =>
                  setImportCategory(event.target.value as KnowledgeCategory)
                }
              >
                {Object.entries(knowledgeCategoryLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            {importMode === "pdf" ? (
              <div className="md:col-span-2">
                <Label htmlFor="knowledge-import-file">PDF máximo 5 MB</Label>
                <Input
                  id="knowledge-import-file"
                  type="file"
                  accept="application/pdf"
                  className="mt-1.5"
                  onChange={(event) => {
                    setImportFile(event.target.files?.[0] ?? null);
                    setImportPreview(null);
                  }}
                />
              </div>
            ) : (
              <div className="md:col-span-2">
                <Label htmlFor="knowledge-import-url">URL pública</Label>
                <Input
                  id="knowledge-import-url"
                  className="mt-1.5"
                  placeholder="https://ejemplo.com/pagina"
                  value={importUrl}
                  onChange={(event) => {
                    setImportUrl(event.target.value);
                    setImportPreview(null);
                  }}
                />
              </div>
            )}
            <div>
              <Label htmlFor="knowledge-import-title">Título opcional</Label>
              <Input
                id="knowledge-import-title"
                className="mt-1.5"
                value={importTitle}
                onChange={(event) => setImportTitle(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="knowledge-import-priority">Prioridad</Label>
              <Input
                id="knowledge-import-priority"
                type="number"
                className="mt-1.5"
                value={importPriority}
                onChange={(event) => setImportPriority(Number(event.target.value))}
              />
            </div>
            <label className="md:col-span-2 flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
              <input
                type="checkbox"
                checked={importActive}
                onChange={(event) => setImportActive(event.target.checked)}
                className="size-4 accent-[#315efb]"
              />
              Guardar activo para incluirlo en el prompt
            </label>
          </div>
          {importPreview ? (
            <div className="rounded-xl border bg-[#f8faff] p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#27334a]">
                {importPreview.source_type === "pdf" ? (
                  <FileText className="size-4" />
                ) : (
                  <LinkIcon className="size-4" />
                )}
                Preview · {importPreview.character_count} caracteres
              </div>
              <p className="text-sm font-semibold">{importPreview.title}</p>
              <p className="mt-1 truncate text-xs text-[#7a8699]">
                Fuente: {importPreview.source}
              </p>
              <Textarea
                readOnly
                className="mt-3 min-h-64"
                value={importPreview.content}
              />
            </div>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setImportOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={previewImportMutation.isPending}
              onClick={() => previewImportMutation.mutate()}
            >
              <Eye className="size-4" />
              {previewImportMutation.isPending ? "Extrayendo…" : "Previsualizar"}
            </Button>
            <Button
              type="button"
              disabled={!importPreview || saveImportMutation.isPending}
              onClick={() => saveImportMutation.mutate()}
            >
              Guardar importación
            </Button>
          </div>
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
