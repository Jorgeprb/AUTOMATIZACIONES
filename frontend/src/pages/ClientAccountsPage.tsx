import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  Phone,
  Plus,
  ShieldCheck,
  Trash2,
  UserRoundCog,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { listClinics } from "@/api/clinics";
import {
  createPortalUser,
  deletePortalUser,
  listPortalUsers,
  updatePortalUser,
  type PortalMembership,
  type PortalRole,
  type PortalUser,
} from "@/api/users";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

const initialForm = {
  email: "",
  display_name: "",
  role: "clinic_admin" as PortalRole,
  clinic_ids: [] as string[],
  temporary_password: "",
  is_active: true,
};

const roleLabels: Record<PortalRole, string> = {
  super_admin: "Administrador global",
  clinic_admin: "Administrador de clínica",
  operator: "Operador",
  read_only: "Solo lectura",
};

interface PendingAssignment {
  id: string;
  user: PortalUser;
  membership: PortalMembership;
  quantity: number;
  createdAt: string;
}

export function ClientAccountsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<PortalUser | null>(null);
  const [deleting, setDeleting] = useState<PortalUser | null>(null);
  const [form, setForm] = useState(initialForm);
  const usersQuery = useQuery({
    queryKey: ["portal-users"],
    queryFn: listPortalUsers,
  });
  const clinicsQuery = useQuery({
    queryKey: ["clinics", "accounts"],
    queryFn: () => listClinics({ pageSize: 100 }),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        temporary_password: form.temporary_password || null,
      };
      return editing
        ? updatePortalUser(editing.id, payload)
        : createPortalUser(payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["portal-users"] });
      setOpen(false);
      setEditing(null);
      setForm(initialForm);
      toast.success("Usuario guardado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePortalUser(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["portal-users"] });
      setDeleting(null);
      toast.success("Usuario eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const startCreate = () => {
    setEditing(null);
    setForm(initialForm);
    setOpen(true);
  };
  const startEdit = (user: PortalUser) => {
    setEditing(user);
    setForm({
      email: user.email ?? user.username,
      display_name: user.display_name ?? "",
      role: user.role,
      clinic_ids: user.memberships.map((membership) => membership.clinic_id),
      temporary_password: "",
      is_active: user.is_active,
    });
    setOpen(true);
  };

  const pendingAssignments = useMemo<PendingAssignment[]>(() => {
    const unique = new Map<string, PendingAssignment>();
    for (const user of usersQuery.data ?? []) {
      for (const membership of user.memberships) {
        for (const pending of membership.pending_provisioning) {
          if (!unique.has(pending.id)) {
            unique.set(pending.id, {
              id: pending.id,
              user,
              membership,
              quantity: pending.quantity,
              createdAt: pending.created_at,
            });
          }
        }
      }
    }
    return [...unique.values()].sort(
      (left, right) =>
        new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime(),
    );
  }, [usersQuery.data]);

  if (usersQuery.isLoading || clinicsQuery.isLoading) {
    return <LoadingState rows={7} />;
  }
  if (usersQuery.error || clinicsQuery.error) {
    return (
      <ErrorState error={(usersQuery.error || clinicsQuery.error) as Error} />
    );
  }
  const clinics = clinicsQuery.data?.items ?? [];
  const users = usersQuery.data ?? [];

  return (
    <div className="space-y-7">
      <PageHeader
        title="Usuarios y clínicas"
        description="Consulta cada usuario, sus clínicas, sus números y los accesos asignados."
        actions={
          <Button onClick={startCreate}>
            <Plus className="size-4" />
            Nuevo usuario
          </Button>
        }
      />

      {pendingAssignments.length ? (
        <Card className="border-[#efb9c1] bg-[#fff4f5] shadow-sm">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-start gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#ffe0e4] text-[#b62f40]">
                <AlertTriangle className="size-5" />
              </span>
              <div>
                <p className="font-bold text-[#922a38]">
                  {pendingAssignments.length} compra(s) de número pendiente(s) de asignar
                </p>
                <p className="mt-1 text-sm leading-6 text-[#9b4d58]">
                  El pago ya está confirmado y el cliente ha sido informado del plazo de hasta 24 horas.
                </p>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {pendingAssignments.map((item) => (
                <div
                  key={item.id}
                  className="flex flex-col gap-3 rounded-xl border border-[#efc9ce] bg-white p-4 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-[#333c50]">
                      {item.membership.clinic_name}
                    </p>
                    <p className="mt-1 truncate text-sm text-[#758096]">
                      {item.user.display_name || item.user.email || item.user.username}
                      {item.quantity > 1 ? ` · ${item.quantity} números` : ""}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() =>
                      navigate(`/business?provisioning=${item.id}&mode=assign`)
                    }
                  >
                    <Phone className="size-4" />
                    Asignar número
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="rounded-xl border border-[#dbe4ff] bg-[#f3f6ff] p-4 text-sm text-[#415476]">
        <ShieldCheck className="mr-2 inline size-4 text-[#315efb]" />
        Cada usuario solo puede acceder a las clínicas indicadas en sus membresías.
      </div>

      <div className="space-y-4">
        {users.map((user) => (
          <Card key={user.id}>
            <CardContent className="p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#eef2ff] text-[#315efb]">
                  <UserRoundCog className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-bold text-[#263249]">
                      {user.display_name || user.username}
                    </h2>
                    <StatusBadge status={user.is_active ? "success" : "neutral"}>
                      {user.is_active ? "Activo" : "Desactivado"}
                    </StatusBadge>
                    <StatusBadge status={user.google_connected ? "info" : "neutral"}>
                      {user.google_connected ? "Google vinculado" : roleLabels[user.role]}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 text-sm text-[#7d889a]">
                    {user.email || user.username}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button variant="outline" size="sm" onClick={() => startEdit(user)}>
                    Editar
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Eliminar ${user.display_name || user.username}`}
                    onClick={() => setDeleting(user)}
                  >
                    <Trash2 className="size-4 text-[#bd3341]" />
                  </Button>
                </div>
              </div>

              <div className="mt-5 border-t border-[#edf0f4] pt-4">
                <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#98a2b2]">
                  Clínicas y números
                </p>
                {user.role === "super_admin" ? (
                  <div className="rounded-xl border border-dashed border-[#d9e0ea] p-4 text-sm text-[#6f7b90]">
                    Acceso global a todas las clínicas.
                  </div>
                ) : user.memberships.length ? (
                  <div className="grid gap-3 xl:grid-cols-2">
                    {user.memberships.map((membership) => (
                      <div
                        key={membership.clinic_id}
                        className="rounded-xl border border-[#e2e7ef] bg-[#fbfcfe] p-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <Building2 className="size-4 text-[#315efb]" />
                            <p className="font-semibold text-[#344058]">
                              {membership.clinic_name}
                            </p>
                          </div>
                          <span className="text-xs font-medium text-[#7c8799]">
                            {roleLabels[membership.role]}
                          </span>
                        </div>

                        <div className="mt-3 space-y-2">
                          {membership.phone_numbers.length ? (
                            membership.phone_numbers.map((phone) => (
                              <div
                                key={phone.id}
                                className="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm"
                              >
                                <Phone className="size-4 text-[#65748b]" />
                                <span className="font-medium text-[#3b465d]">
                                  {phone.phone_number}
                                </span>
                                <StatusBadge status={phone.is_active ? "success" : "neutral"}>
                                  {phone.is_active ? "Activo" : "Inactivo"}
                                </StatusBadge>
                              </div>
                            ))
                          ) : (
                            <p className="rounded-lg border border-dashed px-3 py-2 text-sm text-[#8892a2]">
                              Sin número asignado
                            </p>
                          )}

                          {membership.pending_provisioning.map((pending) => (
                            <div
                              key={pending.id}
                              className="flex flex-col gap-2 rounded-lg border border-[#efc5cb] bg-[#fff5f6] px-3 py-2 sm:flex-row sm:items-center"
                            >
                              <span className="flex-1 text-sm font-semibold text-[#a33141]">
                                Número comprado · pendiente de asignación
                              </span>
                              <Button
                                size="sm"
                                onClick={() =>
                                  navigate(
                                    `/business?provisioning=${pending.id}&mode=assign`,
                                  )
                                }
                              >
                                Asignar número
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-[#d9e0ea] p-4 text-sm text-[#6f7b90]">
                    Este usuario todavía no tiene clínicas asignadas.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Editar usuario" : "Nuevo usuario"}</DialogTitle>
            <DialogDescription>
              La dirección debe coincidir con la cuenta Google que utilizará el usuario.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Nombre</Label>
              <Input
                value={form.display_name}
                onChange={(event) =>
                  setForm({ ...form, display_name: event.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Permisos</Label>
              <Select
                value={form.role}
                onChange={(event) =>
                  setForm({ ...form, role: event.target.value as PortalRole })
                }
              >
                <option value="clinic_admin">Administrador de clínica</option>
                <option value="operator">Operador</option>
                <option value="read_only">Solo lectura</option>
                <option value="super_admin">Administrador global</option>
              </Select>
            </div>
            {form.role !== "super_admin" ? (
              <div className="space-y-2">
                <Label>Clínicas asignadas</Label>
                <div className="max-h-52 space-y-2 overflow-y-auto rounded-xl border border-[#dfe4ec] p-3">
                  {clinics.map((clinic) => (
                    <label key={clinic.id} className="flex items-center gap-3 text-sm">
                      <input
                        type="checkbox"
                        checked={form.clinic_ids.includes(clinic.id)}
                        onChange={(event) =>
                          setForm({
                            ...form,
                            clinic_ids: event.target.checked
                              ? [...form.clinic_ids, clinic.id]
                              : form.clinic_ids.filter((id) => id !== clinic.id),
                          })
                        }
                      />
                      {clinic.name}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="space-y-2">
              <Label>Contraseña temporal opcional</Label>
              <Input
                type="password"
                value={form.temporary_password}
                onChange={(event) =>
                  setForm({ ...form, temporary_password: event.target.value })
                }
                placeholder="Déjalo vacío para acceso solo con Google"
              />
            </div>
            <label className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(event) =>
                  setForm({ ...form, is_active: event.target.checked })
                }
              />
              Cuenta activa
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button
              disabled={
                saveMutation.isPending || !form.email || !form.display_name
              }
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(value) => !value && setDeleting(null)}
        title="Eliminar usuario"
        description={`Se eliminará el acceso de ${deleting?.display_name || deleting?.username || "este usuario"}.`}
        confirmLabel="Eliminar"
        isPending={deleteMutation.isPending}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </div>
  );
}
