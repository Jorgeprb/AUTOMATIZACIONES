import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CalendarDays,
  ChevronRight,
  CircleAlert,
  MessageSquareText,
  Pencil,
  Phone,
  Plus,
  Sparkles,
  Stethoscope,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { getCalendarStatus } from "@/api/calendar";
import { getClinic, updateClinic } from "@/api/clinics";
import {
  createPhoneNumber,
  deletePhoneNumber,
  listPhoneNumbers,
  updatePhoneNumber,
} from "@/api/phoneNumbers";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ClinicForm } from "@/components/forms/ClinicForm";
import { PhoneNumberForm } from "@/components/forms/PhoneNumberForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import type {
  Clinic,
  ClinicFormValues,
  ClinicPayload,
} from "@/schemas/clinic";
import { normalizeWeeklyHours } from "@/schemas/hours";
import type {
  PhoneNumber as ClinicPhoneNumber,
  PhoneNumberFormValues,
  PhoneNumberPayload,
} from "@/schemas/phoneNumber";

const sections = [
  { label: "Trabajadores", description: "Equipo y horarios", icon: Users, suffix: "workers" },
  { label: "Servicios", description: "Catálogo y precios", icon: Stethoscope, suffix: "services" },
  { label: "Asistente", description: "Modelo, voz y prompts", icon: Bot, suffix: "assistant" },
  { label: "Conocimiento", description: "FAQs y políticas", icon: Sparkles, suffix: "knowledge" },
  { label: "Conversaciones", description: "Llamadas y resultados", icon: MessageSquareText, suffix: "conversations" },
  { label: "Calendario", description: "OAuth y calendarios", icon: CalendarDays, suffix: "calendar" },
];

function clinicFormValues(clinic: Clinic): ClinicFormValues {
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

function clinicPayload(values: ClinicFormValues): ClinicPayload {
  return {
    ...values,
    legal_name: values.legal_name || null,
    address: values.address || null,
    website: values.website || null,
    email: values.email || null,
    description: values.description || null,
    emergency_message: values.emergency_message || null,
  };
}

function phoneValues(phoneNumber: ClinicPhoneNumber): PhoneNumberFormValues {
  return {
    provider: phoneNumber.provider,
    phone_number: phoneNumber.phone_number,
    label: phoneNumber.label,
    sip_target: phoneNumber.sip_target ?? "",
    webhook_url: phoneNumber.webhook_url ?? "",
    is_active: phoneNumber.is_active,
    notes: phoneNumber.notes ?? "",
  };
}

function phonePayload(values: PhoneNumberFormValues): PhoneNumberPayload {
  return {
    ...values,
    sip_target: values.sip_target || null,
    webhook_url: values.webhook_url || null,
    notes: values.notes || null,
  };
}

export function ClinicDetailPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const enabled = Boolean(clinicId);
  const [clinicFormOpen, setClinicFormOpen] = useState(false);
  const [phoneFormOpen, setPhoneFormOpen] = useState(false);
  const [editingPhone, setEditingPhone] = useState<ClinicPhoneNumber | null>(null);
  const [deletingPhone, setDeletingPhone] = useState<ClinicPhoneNumber | null>(null);

  const clinicQuery = useQuery({
    queryKey: ["clinic", clinicId],
    queryFn: () => getClinic(clinicId as string),
    enabled,
  });
  const phonesQuery = useQuery({
    queryKey: ["phone-numbers", clinicId],
    queryFn: () => listPhoneNumbers(clinicId as string),
    enabled,
  });
  const calendarQuery = useQuery({
    queryKey: ["calendar-status", clinicId],
    queryFn: () => getCalendarStatus(clinicId as string),
    enabled,
  });

  const refreshPhones = () =>
    queryClient.invalidateQueries({ queryKey: ["phone-numbers", clinicId] });

  const updateClinicMutation = useMutation({
    mutationFn: (values: ClinicFormValues) =>
      updateClinic(clinicId as string, clinicPayload(values)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["clinic", clinicId] });
      await queryClient.invalidateQueries({ queryKey: ["clinics"] });
      setClinicFormOpen(false);
      toast.success("Clínica actualizada");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const createPhoneMutation = useMutation({
    mutationFn: (values: PhoneNumberFormValues) =>
      createPhoneNumber(clinicId as string, phonePayload(values)),
    onSuccess: async () => {
      await refreshPhones();
      setPhoneFormOpen(false);
      toast.success("Número añadido");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const updatePhoneMutation = useMutation({
    mutationFn: (values: PhoneNumberFormValues) =>
      updatePhoneNumber(
        clinicId as string,
        editingPhone?.id as string,
        phonePayload(values),
      ),
    onSuccess: async () => {
      await refreshPhones();
      setEditingPhone(null);
      setPhoneFormOpen(false);
      toast.success("Número actualizado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deletePhoneMutation = useMutation({
    mutationFn: (phoneId: string) =>
      deletePhoneNumber(clinicId as string, phoneId),
    onSuccess: async () => {
      await refreshPhones();
      setDeletingPhone(null);
      toast.success("Número eliminado");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (clinicQuery.isLoading) return <LoadingState rows={6} />;
  if (clinicQuery.error) return <ErrorState error={clinicQuery.error} />;
  const clinic = clinicQuery.data;
  if (!clinic || !clinicId) return null;

  return (
    <div className="space-y-7">
      <PageHeader
        title={clinic.name}
        description={clinic.description || "Configuración operativa de la clínica."}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={clinic.is_active ? "success" : "neutral"}>
              {clinic.is_active ? "Clínica activa" : "Clínica inactiva"}
            </StatusBadge>
            <Button variant="outline" onClick={() => setClinicFormOpen(true)}>
              <Pencil className="size-4" />
              Editar
            </Button>
          </div>
        }
      />

      {!calendarQuery.data?.connected ? (
        <div className="flex items-start gap-3 rounded-xl border border-[#ffe1a8] bg-[#fff9ed] p-4 text-sm text-[#79591e]">
          <CircleAlert className="mt-0.5 size-5 shrink-0" />
          <div>
            <p className="font-semibold">Google Calendar no está conectado.</p>
            <p className="mt-1">
              El agente no podrá comprobar huecos reales hasta completar OAuth.
            </p>
          </div>
          <Button asChild size="sm" variant="outline" className="ml-auto">
            <Link to={`/clinics/${clinicId}/calendar`}>Configurar</Link>
          </Button>
        </div>
      ) : null}

      <Card>
        <CardContent className="grid gap-5 pt-5 sm:grid-cols-2 xl:grid-cols-4">
          <div><p className="text-xs font-semibold uppercase text-[#8a95a7]">Teléfono</p><p className="mt-2 font-semibold">{clinic.main_phone_number}</p></div>
          <div><p className="text-xs font-semibold uppercase text-[#8a95a7]">Email</p><p className="mt-2 font-semibold">{clinic.email || "—"}</p></div>
          <div><p className="text-xs font-semibold uppercase text-[#8a95a7]">Zona / idioma</p><p className="mt-2 font-semibold">{clinic.timezone} · {clinic.default_language}</p></div>
          <div><p className="text-xs font-semibold uppercase text-[#8a95a7]">Retención</p><p className="mt-2 font-semibold">{clinic.data_retention_days} días</p></div>
          <div className="sm:col-span-2"><p className="text-xs font-semibold uppercase text-[#8a95a7]">Dirección</p><p className="mt-2 font-semibold">{clinic.address || "—"}</p></div>
          <div className="sm:col-span-2"><p className="text-xs font-semibold uppercase text-[#8a95a7]">Web</p><p className="mt-2 font-semibold">{clinic.website || "—"}</p></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Números de teléfono</CardTitle>
            <p className="mt-1 text-sm text-[#758197]">
              Enrutamiento de VoIP Studio, Twilio u otros proveedores.
            </p>
          </div>
          <Button
            onClick={() => {
              setEditingPhone(null);
              setPhoneFormOpen(true);
            }}
          >
            <Plus className="size-4" />
            Añadir número
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {phonesQuery.isLoading ? <LoadingState rows={3} /> : null}
          {phonesQuery.error ? <ErrorState error={phonesQuery.error} /> : null}
          {phonesQuery.data?.items.map((phoneNumber) => (
            <div
              key={phoneNumber.id}
              className="flex flex-col gap-3 rounded-xl border border-[#e5e9f0] p-4 lg:flex-row lg:items-center"
            >
              <div className="grid size-10 place-items-center rounded-xl bg-[#eef2ff] text-[#315efb]">
                <Phone className="size-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-[#27334a]">{phoneNumber.label}</p>
                  <StatusBadge status={phoneNumber.is_active ? "success" : "neutral"}>
                    {phoneNumber.is_active ? "Activo" : "Inactivo"}
                  </StatusBadge>
                  <StatusBadge status={phoneNumber.sip_target ? "info" : "warning"}>
                    {phoneNumber.sip_target ? "SIP configurado" : "Sin SIP target"}
                  </StatusBadge>
                </div>
                <p className="mt-1 text-sm text-[#68748a]">
                  {phoneNumber.phone_number} · {phoneNumber.provider}
                </p>
                <p className="mt-1 truncate text-xs text-[#8a94a5]">
                  {phoneNumber.sip_target || "Añade el destino SIP de OpenAI."}
                </p>
              </div>
              <div className="flex gap-1">
                <Button
                  size="icon"
                  variant="ghost"
                  title="Editar número"
                  onClick={() => {
                    setEditingPhone(phoneNumber);
                    setPhoneFormOpen(true);
                  }}
                >
                  <Pencil className="size-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  title="Eliminar número"
                  onClick={() => setDeletingPhone(phoneNumber)}
                >
                  <Trash2 className="size-4 text-[#bd3341]" />
                </Button>
              </div>
            </div>
          ))}
          {!phonesQuery.isLoading && !phonesQuery.data?.items.length ? (
            <div className="rounded-xl border border-dashed p-5 text-sm text-[#758197]">
              No hay números configurados. Añade el número que recibe las llamadas.
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-[#dce4ff] bg-[#f8faff]">
        <CardContent className="pt-5">
          <h3 className="font-semibold text-[#27334a]">Conectar VoIP Studio con OpenAI SIP</h3>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-[#5f6c83]">
            <li>Mantén el número en VoIP Studio.</li>
            <li>Quita el destino anterior de Retell o LiveKit.</li>
            <li>Configura SIP forwarding a <code>sip:OPENAI_PROJECT_ID@sip.api.openai.com;transport=tls</code>.</li>
            <li>Configura en OpenAI el webhook público <code>/webhooks/openai/realtime</code>.</li>
          </ol>
          <p className="mt-3 text-xs text-[#7f8a9c]">
            Si VoIP Studio no acepta la URI completa, prueba sin el prefijo
            <code> sip:</code> o usa el fallback Asterisk documentado.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sections.map((section) => (
          <Link key={section.suffix} to={`/clinics/${clinicId}/${section.suffix}`}>
            <Card className="group h-full p-5 transition hover:-translate-y-0.5 hover:border-[#cbd6ff]">
              <div className="flex items-center justify-between">
                <div className="grid size-10 place-items-center rounded-xl bg-[#eef2ff] text-[#315efb]">
                  <section.icon className="size-5" />
                </div>
                <ChevronRight className="size-4 text-[#a1a9b6]" />
              </div>
              <h3 className="mt-5 font-semibold text-[#263249]">{section.label}</h3>
              <p className="mt-1 text-sm text-[#778398]">{section.description}</p>
            </Card>
          </Link>
        ))}
      </div>

      <Dialog open={clinicFormOpen} onOpenChange={setClinicFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar clínica</DialogTitle>
            <DialogDescription>
              Datos públicos, horario, privacidad y estado operativo.
            </DialogDescription>
          </DialogHeader>
          <ClinicForm
            defaultValues={clinicFormValues(clinic)}
            onSubmit={(values) => updateClinicMutation.mutateAsync(values)}
            onCancel={() => setClinicFormOpen(false)}
            isPending={updateClinicMutation.isPending}
            submitLabel="Guardar cambios"
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={phoneFormOpen}
        onOpenChange={(open) => {
          setPhoneFormOpen(open);
          if (!open) setEditingPhone(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingPhone ? "Editar número" : "Añadir número"}</DialogTitle>
            <DialogDescription>
              Configura el proveedor y el destino SIP que recibirá las llamadas.
            </DialogDescription>
          </DialogHeader>
          <PhoneNumberForm
            defaultValues={editingPhone ? phoneValues(editingPhone) : undefined}
            onSubmit={(values) =>
              editingPhone
                ? updatePhoneMutation.mutateAsync(values)
                : createPhoneMutation.mutateAsync(values)
            }
            onCancel={() => setPhoneFormOpen(false)}
            isPending={createPhoneMutation.isPending || updatePhoneMutation.isPending}
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deletingPhone)}
        onOpenChange={(open) => {
          if (!open) setDeletingPhone(null);
        }}
        title="Eliminar número"
        description={`Se eliminará ${deletingPhone?.phone_number ?? "este número"}.`}
        confirmLabel="Eliminar"
        isPending={deletePhoneMutation.isPending}
        onConfirm={() => {
          if (deletingPhone) deletePhoneMutation.mutate(deletingPhone.id);
        }}
      />
    </div>
  );
}
