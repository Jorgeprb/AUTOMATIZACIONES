import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Mail, Plus, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { getCommercialSummary } from "@/api/enterprise";
import { createAdditionalClinic } from "@/api/registration";
import { listAllClinics } from "@/api/clinics";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const initialForm = {
  name: "",
  timezone: "Europe/Madrid",
  main_phone_number: "pending",
  email: "",
  address: "",
};

export function CommercialAccountPage() {
  const queryClient = useQueryClient();
  const summary = useQuery({ queryKey: ["billing", "summary"], queryFn: getCommercialSummary });
  const clinics = useQuery({ queryKey: ["clinics", "all"], queryFn: listAllClinics });
  const [form, setForm] = useState(initialForm);
  const createClinic = useMutation({
    mutationFn: () => createAdditionalClinic({
      ...form,
      email: form.email || null,
      address: form.address || null,
    }),
    onSuccess: async () => {
      setForm(initialForm);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["clinics"] }),
        queryClient.invalidateQueries({ queryKey: ["billing", "summary"] }),
      ]);
      toast.success("Clínica creada");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (summary.isLoading || clinics.isLoading) return <LoadingState rows={7} />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;

  const account = summary.data?.account;
  return (
    <div className="space-y-7">
      <PageHeader
        title="Cuenta comercial"
        description="Propietario, clínicas vinculadas y estado general de tu cuenta de Autogal."
      />
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><UserRound className="size-5" />Propietario</CardTitle></CardHeader><CardContent><p className="font-semibold">{account?.owner_name ?? "Sin propietario"}</p><p className="mt-1 flex items-center gap-2 text-sm text-[#6e798d]"><Mail className="size-4" />{account?.owner_email ?? account?.billing_email ?? "—"}</p></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Building2 className="size-5" />Clínicas</CardTitle></CardHeader><CardContent><p className="text-3xl font-bold">{account?.clinic_count ?? clinics.data?.length ?? 0}</p><p className="text-sm text-[#6e798d]">Dentro de esta cuenta comercial</p></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-5" />Estado</CardTitle></CardHeader><CardContent><p className="font-semibold capitalize">{account?.status ?? "pendiente"}</p><p className="text-sm text-[#6e798d]">{summary.data?.can_use_production ? "Producción habilitada" : "Cuenta gratuita o pendiente de activación"}</p></CardContent></Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader><CardTitle>Clínicas vinculadas</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {clinics.data?.map((clinic) => (
              <div key={clinic.id} className="rounded-lg border p-4">
                <div className="flex items-center justify-between gap-3"><strong>{clinic.name}</strong><span className="text-xs font-semibold uppercase text-[#667085]">{clinic.is_active ? "Activa" : "Inactiva"}</span></div>
                <p className="mt-1 text-sm text-[#6e798d]">{clinic.main_phone_number} · {clinic.timezone}</p>
              </div>
            ))}
            {!clinics.data?.length ? <p className="text-sm text-[#788396]">Todavía no hay clínicas.</p> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Plus className="size-5" />Añadir clínica</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div><Label>Nombre</Label><Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
            <div><Label>Zona horaria</Label><Input value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} /></div>
            <div><Label>Teléfono principal</Label><Input value={form.main_phone_number} onChange={(event) => setForm({ ...form, main_phone_number: event.target.value })} /></div>
            <div><Label>Email</Label><Input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></div>
            <div><Label>Dirección</Label><Input value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></div>
            <Button className="w-full" disabled={!form.name.trim() || createClinic.isPending} onClick={() => createClinic.mutate()}>{createClinic.isPending ? "Creando…" : "Crear clínica"}</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
