import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Braces,
  CheckCircle2,
  Eye,
  Link2,
  Pencil,
  Plus,
  Power,
  Trash2,
  Workflow,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ZodError } from "zod";

import {
  createFlow,
  deleteFlow,
  listFlows,
  listFlowTemplates,
  previewFlowPrompt,
  updateFlow,
} from "@/api/flows";
import {
  listAssistantConfigs,
  updateAssistantConfig,
} from "@/api/assistants";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import { parseFlowJson } from "@/schemas/flow";
import type {
  ConversationFlow,
  ConversationFlowDefinition,
  PromptPreview,
} from "@/schemas/domain";

function stepLabel(step: ConversationFlowDefinition["steps"][number]): string {
  if (step.type === "message") return `Mensaje · ${step.text}`;
  if (step.type === "collect") {
    return `Recoger ${step.field}${step.required ? " · obligatorio" : ""}`;
  }
  if (step.type === "tool") return `Tool · ${step.tool_name}`;
  return "Confirmación explícita";
}

export function FlowEditorPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [editingFlow, setEditingFlow] = useState<ConversationFlow | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [jsonText, setJsonText] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [validationError, setValidationError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ConversationFlow | null>(null);
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [selectedFlowId, setSelectedFlowId] = useState("");

  const flowsQuery = useQuery({
    queryKey: ["flows", clinicId],
    queryFn: () => listFlows(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const templatesQuery = useQuery({
    queryKey: ["flow-templates", clinicId],
    queryFn: () => listFlowTemplates(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const configsQuery = useQuery({
    queryKey: ["assistants", clinicId],
    queryFn: () => listAssistantConfigs(clinicId as string),
    enabled: Boolean(clinicId),
  });

  useEffect(() => {
    const config =
      configsQuery.data?.items.find((item) => item.is_active) ??
      configsQuery.data?.items[0];
    if (config && !selectedConfigId) {
      setSelectedConfigId(config.id);
      setSelectedFlowId(config.conversation_flow_id ?? "");
    }
  }, [configsQuery.data, selectedConfigId]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["flows", clinicId] }),
      queryClient.invalidateQueries({ queryKey: ["assistants", clinicId] }),
    ]);
  };

  const openEditor = (
    flow?: ConversationFlow,
    definition?: ConversationFlowDefinition,
    templateDescription?: string,
  ) => {
    setEditingFlow(flow ?? null);
    setName(flow?.name ?? definition?.name ?? "");
    setDescription(flow?.description ?? templateDescription ?? "");
    setJsonText(
      JSON.stringify(flow?.flow_json ?? definition ?? { name: "", steps: [] }, null, 2),
    );
    setIsActive(flow?.is_active ?? true);
    setValidationError("");
    setEditorOpen(true);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      let flowJson: ConversationFlowDefinition;
      try {
        flowJson = parseFlowJson(jsonText);
      } catch (error) {
        const message =
          error instanceof ZodError
            ? error.issues.map((issue) => issue.message).join(". ")
            : "El JSON no es válido.";
        setValidationError(message);
        throw new Error(message);
      }
      if (!name.trim()) throw new Error("El nombre es obligatorio.");
      const payload = {
        name: name.trim(),
        description: description.trim() || null,
        flow_json: flowJson,
        is_active: isActive,
      };
      return editingFlow
        ? updateFlow(clinicId as string, editingFlow.id, payload)
        : createFlow(clinicId as string, payload);
    },
    onSuccess: async () => {
      await refresh();
      setEditorOpen(false);
      setEditingFlow(null);
      toast.success("Flujo guardado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const toggleMutation = useMutation({
    mutationFn: (flow: ConversationFlow) =>
      updateFlow(clinicId as string, flow.id, {
        is_active: !flow.is_active,
      }),
    onSuccess: async () => {
      await refresh();
      toast.success("Estado del flujo actualizado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (flowId: string) => deleteFlow(clinicId as string, flowId),
    onSuccess: async () => {
      setDeleteTarget(null);
      await refresh();
      toast.success("Flujo eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const associateMutation = useMutation({
    mutationFn: () =>
      updateAssistantConfig(clinicId as string, selectedConfigId, {
        conversation_flow_id: selectedFlowId || null,
      }),
    onSuccess: async () => {
      await refresh();
      toast.success("Flujo asociado al asistente");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const previewMutation = useMutation({
    mutationFn: (flowId: string) => {
      if (!selectedConfigId) {
        throw new Error("Selecciona una configuración del asistente.");
      }
      return previewFlowPrompt(
        clinicId as string,
        flowId,
        selectedConfigId,
      );
    },
    onSuccess: setPreview,
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <div className="space-y-7">
      <PageHeader
        title="Flujos conversacionales"
        description="Guías flexibles para ordenar objetivos, datos y herramientas del asistente."
        actions={
          <Button onClick={() => openEditor()}>
            <Plus className="size-4" />
            Nuevo flujo
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Crear desde plantilla</CardTitle>
          <CardDescription>
            La plantilla abre un JSON válido que puedes adaptar antes de guardar.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {templatesQuery.data?.map((template) => (
            <button
              key={template.key}
              type="button"
              className="rounded-xl border border-[#e1e6ee] p-4 text-left transition hover:border-[#9db0f8] hover:bg-[#f8faff]"
              onClick={() =>
                openEditor(undefined, template.flow_json, template.description)
              }
            >
              <Workflow className="size-5 text-[#315efb]" />
              <p className="mt-3 font-semibold text-[#27334a]">{template.name}</p>
              <p className="mt-1 text-xs leading-5 text-[#768297]">
                {template.description}
              </p>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Asociación con AssistantConfig</CardTitle>
          <CardDescription>
            Solo un flujo activo asociado se incorpora al prompt de esa configuración.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <div>
            <Label htmlFor="flow-config">Configuración</Label>
            <Select
              id="flow-config"
              className="mt-1.5"
              value={selectedConfigId}
              onChange={(event) => {
                const configId = event.target.value;
                setSelectedConfigId(configId);
                const config = configsQuery.data?.items.find(
                  (item) => item.id === configId,
                );
                setSelectedFlowId(config?.conversation_flow_id ?? "");
              }}
            >
              <option value="">Selecciona configuración</option>
              {configsQuery.data?.items.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name}{config.is_active ? " · activa" : ""}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="flow-association">Flujo</Label>
            <Select
              id="flow-association"
              className="mt-1.5"
              value={selectedFlowId}
              onChange={(event) => setSelectedFlowId(event.target.value)}
            >
              <option value="">Sin flujo asociado</option>
              {flowsQuery.data?.items.map((flow) => (
                <option key={flow.id} value={flow.id}>
                  {flow.name}{flow.is_active ? "" : " · inactivo"}
                </option>
              ))}
            </Select>
          </div>
          <Button
            disabled={!selectedConfigId || associateMutation.isPending}
            onClick={() => associateMutation.mutate()}
          >
            <Link2 className="size-4" />
            Asociar
          </Button>
        </CardContent>
      </Card>

      {flowsQuery.isLoading ? <LoadingState rows={5} /> : null}
      {flowsQuery.error ? <ErrorState error={flowsQuery.error} /> : null}
      {flowsQuery.data?.items.length ? (
        <div className="grid gap-5 xl:grid-cols-2">
          {flowsQuery.data.items.map((flow) => (
            <Card key={flow.id}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div>
                  <CardTitle>{flow.name}</CardTitle>
                  <CardDescription>
                    {flow.description || "Sin descripción"}
                  </CardDescription>
                </div>
                <StatusBadge status={flow.is_active ? "success" : "neutral"}>
                  {flow.is_active ? "Activo" : "Inactivo"}
                </StatusBadge>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  {flow.flow_json.steps.map((step, index) => (
                    <div
                      key={step.id}
                      className="flex items-start gap-3 rounded-lg bg-[#f7f9fc] px-3 py-2.5"
                    >
                      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-white text-xs font-bold text-[#526078]">
                        {index + 1}
                      </span>
                      <p className="text-sm text-[#46536a]">{stepLabel(step)}</p>
                    </div>
                  ))}
                </div>
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  <Button variant="outline" onClick={() => openEditor(flow)}>
                    <Pencil className="size-4" />
                    Editar
                  </Button>
                  <Button
                    variant="outline"
                    disabled={previewMutation.isPending || !selectedConfigId}
                    onClick={() => previewMutation.mutate(flow.id)}
                  >
                    <Eye className="size-4" />
                    Preview
                  </Button>
                  <Button
                    variant="outline"
                    disabled={toggleMutation.isPending}
                    onClick={() => toggleMutation.mutate(flow)}
                  >
                    {flow.is_active ? (
                      <Power className="size-4" />
                    ) : (
                      <CheckCircle2 className="size-4" />
                    )}
                    {flow.is_active ? "Desactivar" : "Activar"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setDeleteTarget(flow)}
                  >
                    <Trash2 className="size-4" />
                    Borrar
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !flowsQuery.isLoading && !flowsQuery.error ? (
        <EmptyState
          icon={Workflow}
          title="Sin flujos"
          description="Empieza con una plantilla o crea un JSON desde cero."
        />
      ) : null}

      <Dialog
        open={editorOpen}
        onOpenChange={(open) => {
          setEditorOpen(open);
          if (!open) setEditingFlow(null);
        }}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>
              {editingFlow ? "Editar flujo" : "Nuevo flujo"}
            </DialogTitle>
            <DialogDescription>
              El backend valida tipos, campos, IDs y nombres de tools.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="flow-name">Nombre</Label>
              <Input
                id="flow-name"
                className="mt-1.5"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <label className="mt-6 flex h-10 items-center gap-3 rounded-lg border px-3 text-sm font-medium">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
                className="size-4 accent-[#315efb]"
              />
              Flujo activo
            </label>
            <div className="md:col-span-2">
              <Label htmlFor="flow-description">Descripción</Label>
              <Input
                id="flow-description"
                className="mt-1.5"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <Label htmlFor="flow-json" className="flex items-center gap-2">
                <Braces className="size-4" />
                JSON del flujo
              </Label>
              <Textarea
                id="flow-json"
                className="mt-1.5 min-h-[460px] bg-[#111827] font-mono text-xs leading-6 text-[#e5e7eb]"
                value={jsonText}
                onChange={(event) => {
                  setJsonText(event.target.value);
                  setValidationError("");
                }}
              />
              {validationError ? (
                <p className="mt-2 text-sm font-medium text-[#bd3341]">
                  {validationError}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEditorOpen(false)}>
              Cancelar
            </Button>
            <Button
              disabled={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              Guardar flujo
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && setPreview(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Prompt con flujo aplicado</DialogTitle>
            <DialogDescription>
              Preview sin modificar la asociación guardada.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-xl bg-[#111827] p-5 text-xs leading-6 text-[#e5e7eb]">
            {preview?.prompt}
          </pre>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Borrar flujo"
        description="Las configuraciones asociadas quedarán sin flujo."
        confirmLabel="Borrar"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
      />
    </div>
  );
}
