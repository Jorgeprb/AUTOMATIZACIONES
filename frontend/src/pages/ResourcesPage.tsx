import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Link2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  deleteResource,
  listResourceRequirements,
  listResources,
  replaceResourceRequirements,
  saveResource,
  type ClinicResource,
  type ResourceRequirement,
} from "@/api/enterprise";
import { listServices } from "@/api/services";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useClinicRoute } from "@/hooks/useClinicRoute";

const empty = {
  name: "",
  description: "",
  resource_type: "other",
  capacity: 1,
  schedule_json: {},
  is_active: true,
};

export function ResourcesPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ClinicResource | null>(null);
  const [form, setForm] = useState(empty);
  const [serviceId, setServiceId] = useState("");
  const [requirements, setRequirements] = useState<ResourceRequirement[]>([]);

  const resourcesQuery = useQuery({
    queryKey: ["resources", clinicId],
    queryFn: () => listResources(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const servicesQuery = useQuery({
    queryKey: ["services", clinicId, "resource-requirements"],
    queryFn: () => listServices(clinicId as string, true),
    enabled: Boolean(clinicId),
  });
  const requirementsQuery = useQuery({
    queryKey: ["resource-requirements", clinicId, serviceId],
    queryFn: () => listResourceRequirements(clinicId as string, serviceId),
    enabled: Boolean(clinicId && serviceId),
  });
  useEffect(() => {
    setRequirements(requirementsQuery.data ?? []);
  }, [requirementsQuery.data]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["resources", clinicId] });
  const save = useMutation({
    mutationFn: () =>
      saveResource(
        clinicId as string,
        { ...form, description: form.description || null },
        editing?.id,
      ),
    onSuccess: async () => {
      await refresh();
      setOpen(false);
      toast.success("Recurso guardado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteResource(clinicId as string, id),
    onSuccess: async () => {
      await refresh();
      toast.success("Recurso eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const saveRequirements = useMutation({
    mutationFn: () =>
      replaceResourceRequirements(
        clinicId as string,
        serviceId,
        requirements.filter((item) => item.quantity > 0),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["resource-requirements", clinicId, serviceId],
      });
      toast.success("Requisitos de recursos actualizados");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const start = (resource?: ClinicResource) => {
    setEditing(resource ?? null);
    setForm(
      resource
        ? {
            name: resource.name,
            description: resource.description ?? "",
            resource_type: resource.resource_type,
            capacity: resource.capacity,
            schedule_json: resource.schedule_json,
            is_active: resource.is_active,
          }
        : empty,
    );
    setOpen(true);
  };
  const quantityFor = (resourceId: string) =>
    requirements.find((item) => item.resource_id === resourceId)?.quantity ?? 0;
  const updateQuantity = (resourceId: string, quantity: number) => {
    setRequirements((current) => {
      const without = current.filter((item) => item.resource_id !== resourceId);
      return quantity > 0 ? [...without, { resource_id: resourceId, quantity }] : without;
    });
  };

  if (resourcesQuery.isLoading) return <LoadingState rows={6} />;
  if (resourcesQuery.isError)
    return <ErrorState error={resourcesQuery.error} onRetry={() => resourcesQuery.refetch()} />;
  const resources = resourcesQuery.data ?? [];
  const services = servicesQuery.data?.items ?? [];
  return (
    <div className="space-y-7">
      <PageHeader
        title="Recursos"
        description="Sillas, cabinas, máquinas o salas cuya capacidad limita las reservas."
        actions={<Button onClick={() => start()}><Plus className="size-4" />Nuevo recurso</Button>}
      />
      {!resources.length ? (
        <EmptyState
          icon={Box}
          title="Sin recursos limitados"
          description="Añade recursos cuando varios servicios compitan por una capacidad limitada."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {resources.map((resource) => (
            <Card key={resource.id}>
              <CardHeader><CardTitle>{resource.name}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-[#657187]">{resource.description || "Sin descripción"}</p>
                <p className="text-sm">Tipo: <strong>{resource.resource_type}</strong></p>
                <p className="text-sm font-semibold">Capacidad simultánea: {resource.capacity}</p>
                <p className="text-xs text-[#7f8b9f]">{resource.is_active ? "Disponible para reservas" : "Recurso desactivado"}</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => start(resource)}>Editar</Button>
                  <Button size="icon" variant="ghost" onClick={() => remove.mutate(resource.id)}><Trash2 className="size-4" /></Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Link2 className="size-5" />Recursos necesarios por servicio</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <div className="max-w-xl space-y-1.5">
            <Label>Servicio</Label>
            <Select value={serviceId} onChange={(event) => setServiceId(event.target.value)}>
              <option value="">Selecciona un servicio</option>
              {services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
            </Select>
          </div>
          {!serviceId ? (
            <p className="text-sm text-[#68758a]">Selecciona un servicio para definir qué recursos y cantidades consume cada cita.</p>
          ) : requirementsQuery.isLoading ? (
            <LoadingState rows={3} />
          ) : !resources.length ? (
            <p className="text-sm text-[#68758a]">Primero crea al menos un recurso.</p>
          ) : (
            <div className="space-y-3">
              {resources.map((resource) => (
                <div key={resource.id} className="grid items-center gap-3 rounded-xl border p-4 sm:grid-cols-[minmax(0,1fr)_150px]">
                  <div><strong>{resource.name}</strong><p className="text-xs text-[#7b8799]">Capacidad total: {resource.capacity}</p></div>
                  <div><Label className="text-xs">Cantidad por cita</Label><Input type="number" min={0} max={resource.capacity} value={quantityFor(resource.id)} onChange={(event) => updateQuantity(resource.id, Number(event.target.value))} /></div>
                </div>
              ))}
              <Button disabled={saveRequirements.isPending} onClick={() => saveRequirements.mutate()}>{saveRequirements.isPending ? "Guardando…" : "Guardar requisitos"}</Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent><DialogHeader><DialogTitle>{editing ? "Editar recurso" : "Nuevo recurso"}</DialogTitle></DialogHeader><div className="space-y-4">
          <div><Label>Nombre</Label><Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div><Label>Tipo</Label><Select value={form.resource_type} onChange={(event) => setForm({ ...form, resource_type: event.target.value })}><option value="chair">Silla</option><option value="room">Sala</option><option value="booth">Cabina</option><option value="machine">Máquina</option><option value="equipment">Equipo</option><option value="other">Otro</option></Select></div>
          <div><Label>Capacidad simultánea</Label><Input type="number" min={1} value={form.capacity} onChange={(event) => setForm({ ...form, capacity: Number(event.target.value) })} /></div>
          <div><Label>Descripción</Label><Textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />Recurso activo</label>
          <Button className="w-full" onClick={() => save.mutate()} disabled={!form.name || save.isPending}>{save.isPending ? "Guardando…" : "Guardar"}</Button>
        </div></DialogContent>
      </Dialog>
    </div>
  );
}
