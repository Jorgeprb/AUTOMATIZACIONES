import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Pencil, Plus, Stethoscope, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  createService,
  deleteService,
  listServices,
  updateService,
} from "@/api/services";
import { listWorkers } from "@/api/workers";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ServiceForm } from "@/components/forms/ServiceForm";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import { formatCurrency } from "@/lib/format";
import type { Service } from "@/schemas/domain";
import {
  serviceDefaults,
  type ServiceFormValues,
  type ServicePayload,
} from "@/schemas/service";

type ActiveFilter = "all" | "active" | "inactive";

function formValues(service: Service): ServiceFormValues {
  return {
    name: service.name,
    public_name: service.public_name,
    description: service.description ?? "",
    aliases_text: service.aliases_json.join(", "),
    common_phrases_text: service.common_phrases_json.join("\n"),
    keywords_text: service.keywords_json.join(", "),
    disambiguation_instructions: service.disambiguation_instructions ?? "",
    price_text: service.price_text ?? "",
    price_amount: service.price_amount ?? "",
    currency: service.currency,
    duration_minutes: service.duration_minutes,
    buffer_before_minutes: service.buffer_before_minutes,
    buffer_after_minutes: service.buffer_after_minutes,
    requires_worker: service.requires_worker,
    allowed_worker_ids: service.allowed_worker_ids ?? [],
    is_bookable_by_bot: service.is_bookable_by_bot,
    is_active: service.is_active,
  };
}

function payload(values: ServiceFormValues): ServicePayload {
  const list = (value: string): string[] => value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const { aliases_text, common_phrases_text, keywords_text, ...base } = values;
  return {
    ...base,
    aliases_json: list(aliases_text),
    common_phrases_json: list(common_phrases_text),
    keywords_json: list(keywords_text),
    disambiguation_instructions: values.disambiguation_instructions || null,
    description: values.description || null,
    price_text: values.price_text || null,
    price_amount: values.price_amount || null,
    currency: values.currency.toUpperCase(),
    allowed_worker_ids:
      values.requires_worker && values.allowed_worker_ids.length
        ? values.allowed_worker_ids
        : null,
  };
}

function visiblePrice(service: Service): string {
  if (service.price_text) return service.price_text;
  if (service.price_amount !== null) {
    return formatCurrency(service.price_amount, service.currency);
  }
  return "Precio no especificado";
}

export function ServicesPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editingService, setEditingService] = useState<Service | null>(null);
  const [deletingService, setDeletingService] = useState<Service | null>(null);
  const isActive =
    activeFilter === "all" ? undefined : activeFilter === "active";

  const query = useQuery({
    queryKey: ["services", clinicId, activeFilter],
    queryFn: () => listServices(clinicId as string, isActive),
    enabled: Boolean(clinicId),
  });
  const workersQuery = useQuery({
    queryKey: ["workers", clinicId],
    queryFn: () => listWorkers(clinicId as string, true),
    enabled: Boolean(clinicId),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["services", clinicId] });
  };
  const createMutation = useMutation({
    mutationFn: (values: ServiceFormValues) =>
      createService(clinicId as string, payload(values)),
    onSuccess: async () => {
      await refresh();
      setFormOpen(false);
      toast.success("Servicio creado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const updateMutation = useMutation({
    mutationFn: (values: ServiceFormValues) =>
      updateService(
        clinicId as string,
        editingService?.id as string,
        payload(values),
      ),
    onSuccess: async () => {
      await refresh();
      setEditingService(null);
      setFormOpen(false);
      toast.success("Servicio actualizado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (serviceId: string) =>
      deleteService(clinicId as string, serviceId),
    onSuccess: async () => {
      await refresh();
      setDeletingService(null);
      toast.success("Servicio eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const columns = useMemo<Array<DataTableColumn<Service>>>(
    () => [
      {
        key: "name",
        header: "Servicio",
        cell: (service) => (
          <div>
            <p className="font-semibold text-[#263249]">{service.public_name}</p>
            <p className="mt-1 text-xs text-[#7b8799]">
              Interno: {service.name}
            </p>
            {service.description ? (
              <p className="mt-1 max-w-md truncate text-xs text-[#7b8799]">
                {service.description}
              </p>
            ) : null}
          </div>
        ),
      },
      {
        key: "duration",
        header: "Duración",
        cell: (service) => {
          const total =
            service.duration_minutes +
            service.buffer_before_minutes +
            service.buffer_after_minutes;
          return (
            <div>
              <p>{service.duration_minutes} min</p>
              <p className="mt-1 text-xs text-[#7b8799]">
                Total con buffers: {total} min
              </p>
              {service.duration_minutes <= 0 ? (
                <p className="mt-1 text-xs font-medium text-[#b46a13]">
                  Este servicio no tiene duración
                </p>
              ) : null}
            </div>
          );
        },
      },
      {
        key: "price",
        header: "Precio visible",
        cell: (service) => (
          <div>
            <p>{visiblePrice(service)}</p>
            {!service.price_text && service.price_amount === null ? (
              <p className="mt-1 text-xs font-medium text-[#b46a13]">
                Este servicio no tiene precio
              </p>
            ) : null}
          </div>
        ),
      },
      {
        key: "bot",
        header: "Asistente",
        cell: (service) => (
          <StatusBadge status={service.is_bookable_by_bot ? "success" : "neutral"}>
            {service.is_bookable_by_bot ? "Reservable" : "No reservable"}
          </StatusBadge>
        ),
      },
      {
        key: "status",
        header: "Estado",
        cell: (service) => (
          <StatusBadge status={service.is_active ? "success" : "neutral"}>
            {service.is_active ? "Activo" : "Inactivo"}
          </StatusBadge>
        ),
      },
      {
        key: "actions",
        header: "",
        className: "w-[100px]",
        cell: (service) => (
          <div className="flex justify-end">
            <Button
              size="icon"
              variant="ghost"
              title="Editar servicio"
              onClick={() => {
                setEditingService(service);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title="Eliminar servicio"
              onClick={() => setDeletingService(service)}
            >
              <Trash2 className="size-4 text-[#bd3341]" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const noBookable =
    query.data?.items.filter((service) => service.is_active).length &&
    !query.data.items.some(
      (service) => service.is_active && service.is_bookable_by_bot,
    );

  return (
    <div className="space-y-7">
      <PageHeader
        title="Servicios y precios"
        description="Catálogo que el asistente puede explicar y, cuando corresponda, reservar."
        actions={
          <Button
            onClick={() => {
              setEditingService(null);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            Nuevo servicio
          </Button>
        }
      />

      <div className="flex justify-end">
        <Select
          aria-label="Filtrar servicios por estado"
          className="w-48"
          value={activeFilter}
          onChange={(event) => setActiveFilter(event.target.value as ActiveFilter)}
        >
          <option value="all">Todos</option>
          <option value="active">Activos</option>
          <option value="inactive">Inactivos</option>
        </Select>
      </div>

      {noBookable ? (
        <div className="flex items-start gap-3 rounded-xl border border-[#ffe0a5] bg-[#fff9ec] p-4 text-sm text-[#78591d]">
          <AlertTriangle className="mt-0.5 size-5 shrink-0" />
          No hay servicios reservables. El asistente podrá informar, pero no
          ofrecer citas.
        </div>
      ) : null}

      {query.isLoading ? <LoadingState rows={6} /> : null}
      {query.error ? <ErrorState error={query.error} /> : null}
      {query.data?.items.length ? (
        <DataTable columns={columns} rows={query.data.items} rowKey={(row) => row.id} />
      ) : !query.isLoading && !query.error ? (
        <EmptyState
          icon={Stethoscope}
          title="Sin servicios"
          description="Crea servicios, precios y duración para dar contexto al asistente."
          action={
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="size-4" />
              Crear servicio
            </Button>
          }
        />
      ) : null}

      <Dialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingService(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingService ? "Editar servicio" : "Nuevo servicio"}
            </DialogTitle>
            <DialogDescription>
              Define qué puede comunicar y reservar el asistente.
            </DialogDescription>
          </DialogHeader>
          <ServiceForm
            workers={workersQuery.data?.items ?? []}
            defaultValues={
              editingService ? formValues(editingService) : serviceDefaults
            }
            onSubmit={(values) =>
              editingService
                ? updateMutation.mutateAsync(values)
                : createMutation.mutateAsync(values)
            }
            onCancel={() => setFormOpen(false)}
            isPending={createMutation.isPending || updateMutation.isPending}
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deletingService)}
        onOpenChange={(open) => {
          if (!open) setDeletingService(null);
        }}
        title="Eliminar servicio"
        description={`Se eliminará ${deletingService?.public_name ?? "este servicio"}. Las citas históricas conservarán su registro.`}
        confirmLabel="Eliminar"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deletingService) deleteMutation.mutate(deletingService.id);
        }}
      />
    </div>
  );
}
