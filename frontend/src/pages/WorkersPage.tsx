import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarX2, Pencil, Plus, Trash2, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  createWorker,
  deleteWorker,
  listWorkers,
  updateWorker,
} from "@/api/workers";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { WorkerForm } from "@/components/forms/WorkerForm";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import type { Worker } from "@/schemas/domain";
import { normalizeWeeklyHours } from "@/schemas/hours";
import {
  workerDefaults,
  type WorkerFormValues,
  type WorkerPayload,
} from "@/schemas/worker";

function formValues(worker: Worker): WorkerFormValues {
  return {
    name: worker.name,
    role: worker.role,
    public_description: worker.public_description ?? "",
    email: worker.email ?? "",
    phone_extension: worker.phone_extension ?? "",
    calendar_id: worker.calendar_id ?? "",
    color_id: worker.color_id ?? "",
    is_active: worker.is_active,
    working_hours_json: normalizeWeeklyHours(worker.working_hours_json),
  };
}

function payload(values: WorkerFormValues): WorkerPayload {
  return {
    ...values,
    public_description: values.public_description || null,
    email: values.email || null,
    phone_extension: values.phone_extension || null,
    calendar_id: values.calendar_id || null,
    color_id: values.color_id || null,
  };
}

export function WorkersPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editingWorker, setEditingWorker] = useState<Worker | null>(null);
  const [deletingWorker, setDeletingWorker] = useState<Worker | null>(null);

  const query = useQuery({
    queryKey: ["workers", clinicId],
    queryFn: () => listWorkers(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["workers", clinicId] });
    await queryClient.invalidateQueries({ queryKey: ["calendar-status", clinicId] });
  };
  const createMutation = useMutation({
    mutationFn: (values: WorkerFormValues) =>
      createWorker(clinicId as string, payload(values)),
    onSuccess: async () => {
      await refresh();
      setFormOpen(false);
      toast.success("Trabajador creado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const updateMutation = useMutation({
    mutationFn: (values: WorkerFormValues) =>
      updateWorker(
        clinicId as string,
        editingWorker?.id as string,
        payload(values),
      ),
    onSuccess: async () => {
      await refresh();
      setEditingWorker(null);
      setFormOpen(false);
      toast.success("Trabajador actualizado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (workerId: string) =>
      deleteWorker(clinicId as string, workerId),
    onSuccess: async () => {
      await refresh();
      setDeletingWorker(null);
      toast.success("Trabajador eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const columns = useMemo<Array<DataTableColumn<Worker>>>(
    () => [
      {
        key: "name",
        header: "Trabajador",
        cell: (worker) => (
          <div>
            <p className="font-semibold text-[#263249]">{worker.name}</p>
            <p className="mt-1 text-xs text-[#7b8799]">{worker.role}</p>
          </div>
        ),
      },
      {
        key: "description",
        header: "Descripción pública",
        cell: (worker) => worker.public_description || "—",
      },
      {
        key: "contact",
        header: "Contacto",
        cell: (worker) => (
          <div>
            <p>{worker.email || "—"}</p>
            <p className="mt-1 text-xs text-[#7b8799]">
              Ext. {worker.phone_extension || "—"}
            </p>
          </div>
        ),
      },
      {
        key: "status",
        header: "Estado operativo",
        cell: (worker) => (
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={worker.is_active ? "success" : "neutral"}>
              {worker.is_active ? "Activo" : "Inactivo"}
            </StatusBadge>
            <StatusBadge status={worker.calendar_id ? "info" : "warning"}>
              {worker.calendar_id ? "Calendario conectado" : "Sin calendario"}
            </StatusBadge>
          </div>
        ),
      },
      {
        key: "actions",
        header: "",
        className: "w-[100px]",
        cell: (worker) => (
          <div className="flex justify-end">
            <Button
              size="icon"
              variant="ghost"
              title="Editar trabajador"
              onClick={() => {
                setEditingWorker(worker);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title="Eliminar trabajador"
              onClick={() => setDeletingWorker(worker)}
            >
              <Trash2 className="size-4 text-[#bd3341]" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-7">
      <PageHeader
        title="Trabajadores"
        description="Equipo, perfil público, horarios laborales y estado de calendario."
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link to={`/clinics/${clinicId}/calendar`}>Gestionar calendarios</Link>
            </Button>
            <Button
              onClick={() => {
                setEditingWorker(null);
                setFormOpen(true);
              }}
            >
              <Plus className="size-4" />
              Nuevo trabajador
            </Button>
          </div>
        }
      />
      {query.isLoading ? <LoadingState rows={6} /> : null}
      {query.error ? <ErrorState error={query.error} /> : null}
      {query.data?.items.length ? (
        <DataTable columns={columns} rows={query.data.items} rowKey={(row) => row.id} />
      ) : !query.isLoading && !query.error ? (
        <EmptyState
          icon={Users}
          title="Sin trabajadores"
          description="Crea el primer trabajador y define su horario semanal."
          action={
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="size-4" />
              Crear trabajador
            </Button>
          }
        />
      ) : null}
      {query.data?.items.some((worker) => !worker.calendar_id) ? (
        <div className="flex items-start gap-3 rounded-xl border border-[#ffe3b4] bg-[#fffaf0] p-4 text-sm text-[#7b5b21]">
          <CalendarX2 className="mt-0.5 size-5 shrink-0" />
          Los trabajadores sin calendario no recibirán huecos reales del agente.
        </div>
      ) : null}

      <Dialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingWorker(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingWorker ? "Editar trabajador" : "Nuevo trabajador"}
            </DialogTitle>
            <DialogDescription>
              Define datos públicos, horario y estado operativo.
            </DialogDescription>
          </DialogHeader>
          <WorkerForm
            defaultValues={editingWorker ? formValues(editingWorker) : workerDefaults}
            onSubmit={(values) =>
              editingWorker
                ? updateMutation.mutateAsync(values)
                : createMutation.mutateAsync(values)
            }
            onCancel={() => setFormOpen(false)}
            isPending={createMutation.isPending || updateMutation.isPending}
            submitLabel={editingWorker ? "Guardar cambios" : "Crear trabajador"}
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deletingWorker)}
        onOpenChange={(open) => {
          if (!open) setDeletingWorker(null);
        }}
        title="Eliminar trabajador"
        description={`Se eliminará ${deletingWorker?.name ?? "este trabajador"}. Las citas existentes pueden impedirlo.`}
        confirmLabel="Eliminar"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deletingWorker) deleteMutation.mutate(deletingWorker.id);
        }}
      />
    </div>
  );
}
