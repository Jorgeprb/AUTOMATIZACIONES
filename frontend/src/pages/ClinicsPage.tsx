import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ExternalLink, Pencil, Plus, Trash2 } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  createClinic,
  deleteClinic,
  listClinics,
  updateClinic,
} from "@/api/clinics";
import { createAdditionalClinic } from "@/api/registration";
import { ClinicForm } from "@/components/forms/ClinicForm";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useActiveClinic } from "@/hooks/useActiveClinic";
import { useCommercialAccess } from "@/hooks/useCommercialAccess";
import { formatDate } from "@/lib/format";
import { getCurrentAdmin } from "@/lib/auth";
import { isClientPortal } from "@/lib/portal";
import {
  clinicDefaults,
  type Clinic,
  type ClinicFormValues,
  type ClinicPayload,
} from "@/schemas/clinic";
import { normalizeWeeklyHours } from "@/schemas/hours";

function formValues(clinic: Clinic): ClinicFormValues {
  return {
    name: clinic.name,
    legal_name: clinic.legal_name ?? "",
    timezone: clinic.timezone,
    default_language: clinic.default_language,
    main_phone_number: clinic.main_phone_number,
    address: clinic.address ?? "",
    website: clinic.website ?? "",
    email: clinic.email ?? "",
    description: clinic.description ?? "",
    emergency_message: clinic.emergency_message ?? "",
    opening_hours_json: normalizeWeeklyHours(clinic.opening_hours_json),
    data_retention_days: clinic.data_retention_days,
    is_active: clinic.is_active,
  };
}

function payload(values: ClinicFormValues): ClinicPayload {
  return {
    ...values,
    legal_name: values.legal_name || null,
    address: values.address || null,
    website: values.website || null,
    email: values.email || null,
    description: values.description || null,
    emergency_message: values.emergency_message || null,
    opening_hours_json: values.opening_hours_json,
  };
}

export function ClinicsPage() {
  const queryClient = useQueryClient();
  const { activeClinicId, setActiveClinicId } = useActiveClinic();
  const access = useCommercialAccess();
  const [editingClinic, setEditingClinic] = useState<Clinic | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [deletingClinic, setDeletingClinic] = useState<Clinic | null>(null);
  const authQuery = useQuery({ queryKey: ["auth", "me"], queryFn: getCurrentAdmin, staleTime: 60_000 });
  const canManageTenants = authQuery.data?.role === "super_admin";
  const canCreateClinic = canManageTenants || isClientPortal;

  const clinicsQuery = useQuery({
    queryKey: ["clinics", "admin-list"],
    queryFn: () => listClinics({ pageSize: 100 }),
  });

  const refreshClinics = async () => {
    await queryClient.invalidateQueries({ queryKey: ["clinics"] });
  };

  const createMutation = useMutation({
    mutationFn: async (values: ClinicPayload) => {
      if (isClientPortal) {
        const result = await createAdditionalClinic({
          name: values.name,
          timezone: values.timezone,
          main_phone_number: values.main_phone_number,
          email: values.email,
          address: values.address,
        });
        return result.clinic_id;
      }
      const clinic = await createClinic(values);
      return clinic.id;
    },
    onSuccess: async (clinicId) => {
      await refreshClinics();
      setActiveClinicId(clinicId);
      setFormOpen(false);
      toast.success("Clínica creada");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      clinicId,
      values,
    }: {
      clinicId: string;
      values: ClinicPayload;
    }) => updateClinic(clinicId, values),
    onSuccess: async () => {
      await refreshClinics();
      setFormOpen(false);
      setEditingClinic(null);
      toast.success("Clínica actualizada");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteClinic,
    onSuccess: async (_, clinicId) => {
      if (activeClinicId === clinicId) setActiveClinicId(null);
      await refreshClinics();
      setDeletingClinic(null);
      toast.success("Clínica eliminada");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const handleSubmit = async (values: ClinicFormValues) => {
    if (editingClinic) {
      await updateMutation.mutateAsync({
        clinicId: editingClinic.id,
        values: payload(values),
      });
    } else {
      await createMutation.mutateAsync(payload(values));
    }
  };

  const columns = useMemo<Array<DataTableColumn<Clinic>>>(
    () => [
      {
        key: "clinic",
        header: "Clínica",
        cell: (clinic) => (
          <div>
            <Link
              className="font-semibold text-[#263249] hover:text-[#315efb]"
              to={isClientPortal && !access.unlocked ? "/" : `/clinics/${clinic.id}/settings/general`}
              onClick={() => setActiveClinicId(clinic.id)}
            >
              {clinic.name}
            </Link>
            <p className="mt-1 text-xs text-[#7d889a]">
              {clinic.legal_name || "Sin razón social"}
            </p>
          </div>
        ),
      },
      {
        key: "phone",
        header: "Teléfono",
        cell: (clinic) =>
          clinic.main_phone_number.startsWith("pending-")
            ? "Pendiente de asignación"
            : clinic.main_phone_number,
      },
      {
        key: "timezone",
        header: "Zona horaria",
        cell: (clinic) => (
          <div>
            <p>{clinic.timezone}</p>
            <p className="mt-1 text-xs uppercase text-[#8893a5]">
              {clinic.default_language}
            </p>
          </div>
        ),
      },
      {
        key: "status",
        header: "Estado",
        cell: (clinic) => (
          <StatusBadge status={clinic.is_active ? "success" : "neutral"}>
            {clinic.is_active ? "Activa" : "Inactiva"}
          </StatusBadge>
        ),
      },
      {
        key: "created",
        header: "Creada",
        cell: (clinic) => formatDate(clinic.created_at),
      },
      {
        key: "actions",
        header: "",
        className: "w-[140px]",
        cell: (clinic) => (
          <div className="flex justify-end gap-1">
            <Button asChild size="icon" variant="ghost" title="Abrir">
              <Link
                to={isClientPortal && !access.unlocked ? "/" : `/clinics/${clinic.id}/settings/general`}
                onClick={() => setActiveClinicId(clinic.id)}
              >
                <ExternalLink className="size-4" />
              </Link>
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title="Editar"
              onClick={() => {
                setEditingClinic(clinic);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            {canManageTenants ? <Button size="icon" variant="ghost" title="Eliminar" onClick={() => setDeletingClinic(clinic)}><Trash2 className="size-4 text-[#bd3341]" /></Button> : null}
          </div>
        ),
      },
    ],
    [access.unlocked, canManageTenants, setActiveClinicId],
  );

  return (
    <div className="space-y-7">
      <PageHeader
        title={isClientPortal ? "Mis clínicas" : "Clínicas"}
        description={isClientPortal ? "Accede a los datos y configuraciones de las clínicas asignadas a tu cuenta." : "Gestiona los tenants, datos públicos y estado operativo de la plataforma."}
        actions={canCreateClinic ?
          <Button
            size={isClientPortal ? "icon" : "default"}
            title={isClientPortal ? "Añadir clínica" : undefined}
            aria-label={isClientPortal ? "Añadir clínica" : undefined}
            onClick={() => {
              setEditingClinic(null);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            {!isClientPortal ? "Nueva clínica" : null}
          </Button>
        : undefined}
      />

      {clinicsQuery.isLoading ? <LoadingState rows={6} /> : null}
      {clinicsQuery.error ? (
        <ErrorState
          error={clinicsQuery.error}
          onRetry={() => void clinicsQuery.refetch()}
        />
      ) : null}
      {!clinicsQuery.isLoading && !clinicsQuery.error ? (
        clinicsQuery.data?.items.length ? (
          <DataTable
            columns={columns}
            rows={clinicsQuery.data.items}
            rowKey={(clinic) => clinic.id}
          />
        ) : (
          <EmptyState
            icon={Building2}
            title="No hay clínicas"
            description="Crea la primera clínica para empezar a configurar el asistente."
            action={canCreateClinic ? <Button onClick={() => setFormOpen(true)}><Plus className="size-4" />Crear clínica</Button> : undefined}
          />
        )
      ) : null}

      <Dialog
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingClinic(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingClinic ? "Editar clínica" : "Nueva clínica"}
            </DialogTitle>
            <DialogDescription>
              Configura los datos básicos que utilizarán el panel y el asistente.
            </DialogDescription>
          </DialogHeader>
          {isClientPortal ? (
            <ClientClinicForm
              clinic={editingClinic}
              isPending={createMutation.isPending || updateMutation.isPending}
              onCancel={() => setFormOpen(false)}
              onSubmit={handleSubmit}
            />
          ) : (
            <ClinicForm
              defaultValues={editingClinic ? formValues(editingClinic) : clinicDefaults}
              onSubmit={handleSubmit}
              onCancel={() => setFormOpen(false)}
              isPending={createMutation.isPending || updateMutation.isPending}
              submitLabel={editingClinic ? "Guardar cambios" : "Crear clínica"}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deletingClinic)}
        onOpenChange={(open) => {
          if (!open) setDeletingClinic(null);
        }}
        title="Eliminar clínica"
        description={`Se eliminará ${deletingClinic?.name ?? "esta clínica"} y su configuración asociada. Las relaciones restringidas pueden impedir la operación.`}
        confirmLabel="Eliminar"
        isPending={deleteMutation.isPending}
        onConfirm={() => {
          if (deletingClinic) deleteMutation.mutate(deletingClinic.id);
        }}
      />
    </div>
  );
}

function ClientClinicForm({
  clinic,
  isPending,
  onCancel,
  onSubmit,
}: {
  clinic: Clinic | null;
  isPending: boolean;
  onCancel: () => void;
  onSubmit: (values: ClinicFormValues) => Promise<void>;
}) {
  const [values, setValues] = useState({
    name: clinic?.name ?? "",
    timezone: clinic?.timezone ?? "Europe/Madrid",
    email: clinic?.email ?? "",
    address: clinic?.address ?? "",
  });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onSubmit({
      ...clinicDefaults,
      name: values.name.trim(),
      timezone: values.timezone.trim(),
      main_phone_number: clinic?.main_phone_number || "pending",
      email: values.email.trim(),
      address: values.address.trim(),
    });
  };

  return (
    <form className="space-y-4" onSubmit={(event) => void submit(event)}>
      <div className="space-y-1.5">
        <Label htmlFor="new-clinic-name">Nombre</Label>
        <Input
          id="new-clinic-name"
          required
          maxLength={200}
          value={values.name}
          onChange={(event) => setValues({ ...values, name: event.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="new-clinic-timezone">Zona horaria</Label>
        <Input
          id="new-clinic-timezone"
          required
          maxLength={64}
          value={values.timezone}
          onChange={(event) => setValues({ ...values, timezone: event.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="new-clinic-email">Email</Label>
        <Input
          id="new-clinic-email"
          type="email"
          maxLength={320}
          value={values.email}
          onChange={(event) => setValues({ ...values, email: event.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="new-clinic-address">Dirección</Label>
        <Input
          id="new-clinic-address"
          value={values.address}
          onChange={(event) => setValues({ ...values, address: event.target.value })}
        />
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isPending || !values.name.trim()}>
          {isPending ? "Guardando…" : clinic ? "Guardar cambios" : "Crear clínica"}
        </Button>
      </div>
    </form>
  );
}
