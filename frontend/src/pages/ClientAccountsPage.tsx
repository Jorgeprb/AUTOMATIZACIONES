import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { listClinics } from "@/api/clinics";
import { createPortalUser, deletePortalUser, listPortalUsers, updatePortalUser, type PortalRole, type PortalUser } from "@/api/users";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

const initialForm = { email: "", display_name: "", role: "clinic_admin" as PortalRole, clinic_ids: [] as string[], temporary_password: "", is_active: true };

export function ClientAccountsPage() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<PortalUser | null>(null);
  const [deleting, setDeleting] = useState<PortalUser | null>(null);
  const [form, setForm] = useState(initialForm);
  const usersQuery = useQuery({ queryKey: ["portal-users"], queryFn: listPortalUsers });
  const clinicsQuery = useQuery({ queryKey: ["clinics", "accounts"], queryFn: () => listClinics({ pageSize: 100 }) });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = { ...form, temporary_password: form.temporary_password || null };
      return editing ? updatePortalUser(editing.id, payload) : createPortalUser(payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["portal-users"] });
      setOpen(false); setEditing(null); setForm(initialForm); toast.success("Acceso guardado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePortalUser(id),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["portal-users"] }); setDeleting(null); toast.success("Cuenta eliminada"); },
    onError: (error: Error) => toast.error(error.message),
  });

  const startCreate = () => { setEditing(null); setForm(initialForm); setOpen(true); };
  const startEdit = (user: PortalUser) => {
    setEditing(user);
    setForm({ email: user.email ?? user.username, display_name: user.display_name ?? "", role: user.role, clinic_ids: user.memberships.map((m) => m.clinic_id), temporary_password: "", is_active: user.is_active });
    setOpen(true);
  };
  const columns = useMemo<Array<DataTableColumn<PortalUser>>>(() => [
    { key: "user", header: "Cliente", cell: (user) => <div><p className="font-semibold text-[#263249]">{user.display_name || user.username}</p><p className="text-xs text-[#7d889a]">{user.email || user.username}</p></div> },
    { key: "clinics", header: "Clínicas", cell: (user) => user.role === "super_admin" ? "Todas" : user.memberships.map((m) => m.clinic_name).join(", ") || "Sin clínicas" },
    { key: "google", header: "Google", cell: (user) => <StatusBadge status={user.google_connected ? "success" : "neutral"}>{user.google_connected ? "Vinculado" : "Pendiente"}</StatusBadge> },
    { key: "status", header: "Estado", cell: (user) => <StatusBadge status={user.is_active ? "success" : "neutral"}>{user.is_active ? "Activo" : "Desactivado"}</StatusBadge> },
    { key: "actions", header: "", cell: (user) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => startEdit(user)}>Editar</Button><Button variant="ghost" size="icon" onClick={() => setDeleting(user)}><Trash2 className="size-4 text-[#bd3341]" /></Button></div> },
  ], []);

  if (usersQuery.isLoading || clinicsQuery.isLoading) return <LoadingState rows={6} />;
  if (usersQuery.error || clinicsQuery.error) return <ErrorState error={(usersQuery.error || clinicsQuery.error) as Error} />;
  const clinics = clinicsQuery.data?.items ?? [];

  return <div className="space-y-7">
    <PageHeader title="Clientes y accesos" description="Invita cuentas y decide qué clínicas puede gestionar cada cliente." actions={<Button onClick={startCreate}><Plus className="size-4" />Nuevo acceso</Button>} />
    <div className="rounded-xl border border-[#dbe4ff] bg-[#f3f6ff] p-4 text-sm text-[#415476]"><ShieldCheck className="mr-2 inline size-4 text-[#315efb]" />El cliente inicia sesión con su cuenta Google y solo recibe las clínicas asignadas.</div>
    <DataTable columns={columns} rows={usersQuery.data ?? []} rowKey={(user) => user.id} />
    <Dialog open={open} onOpenChange={setOpen}><DialogContent><DialogHeader><DialogTitle>{editing ? "Editar acceso" : "Nuevo acceso de cliente"}</DialogTitle><DialogDescription>La dirección debe coincidir con la cuenta Google que utilizará el cliente.</DialogDescription></DialogHeader>
      <div className="space-y-4">
        <div className="space-y-2"><Label>Email</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        <div className="space-y-2"><Label>Nombre</Label><Input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></div>
        <div className="space-y-2"><Label>Permisos</Label><Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as PortalRole })}><option value="clinic_admin">Administrador de clínica</option><option value="operator">Operador</option><option value="read_only">Solo lectura</option><option value="super_admin">Administrador global</option></Select></div>
        {form.role !== "super_admin" ? <div className="space-y-2"><Label>Clínicas asignadas</Label><div className="max-h-52 space-y-2 overflow-y-auto rounded-xl border border-[#dfe4ec] p-3">{clinics.map((clinic) => <label key={clinic.id} className="flex items-center gap-3 text-sm"><input type="checkbox" checked={form.clinic_ids.includes(clinic.id)} onChange={(e) => setForm({ ...form, clinic_ids: e.target.checked ? [...form.clinic_ids, clinic.id] : form.clinic_ids.filter((id) => id !== clinic.id) })} />{clinic.name}</label>)}</div></div> : null}
        <div className="space-y-2"><Label>Contraseña temporal opcional</Label><Input type="password" value={form.temporary_password} onChange={(e) => setForm({ ...form, temporary_password: e.target.value })} placeholder="Déjalo vacío para acceso solo con Google" /></div>
        <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Cuenta activa</label>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button><Button disabled={saveMutation.isPending || !form.email || !form.display_name} onClick={() => saveMutation.mutate()}>{saveMutation.isPending ? "Guardando…" : "Guardar"}</Button></DialogFooter>
    </DialogContent></Dialog>
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(value) => !value && setDeleting(null)} title="Eliminar cuenta" description={`Se eliminará el acceso de ${deleting?.display_name || deleting?.username || "este cliente"}.`} confirmLabel="Eliminar" isPending={deleteMutation.isPending} onConfirm={() => deleting && deleteMutation.mutate(deleting.id)} />
  </div>;
}
