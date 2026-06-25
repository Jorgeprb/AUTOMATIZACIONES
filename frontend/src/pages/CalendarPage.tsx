import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarCheck2,
  CheckCircle2,
  Link2,
  RefreshCw,
  Search,
  Unlink,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { apiConfig } from "@/api/client";
import {
  cancelAppointment,
  listAppointments,
  type AppointmentFilters,
} from "@/api/appointments";
import {
  createWorkerCalendar,
  getCalendarStatus,
  linkWorkerCalendar,
  listCalendars,
  testWorkerFreeBusy,
} from "@/api/calendar";
import { listWorkers } from "@/api/workers";
import { listServices } from "@/api/services";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import { formatDateTime } from "@/lib/format";
import type { AppointmentAnalysis } from "@/schemas/domain";

interface WorkerCalendarSelection {
  calendarId: string;
  colorId: string;
}

export function CalendarPage() {
  const clinicId = useClinicRoute();
  const queryClient = useQueryClient();
  const enabled = Boolean(clinicId);
  const [selections, setSelections] = useState<
    Record<string, WorkerCalendarSelection>
  >({});
  const [appointmentFilters, setAppointmentFilters] =
    useState<AppointmentFilters>({ pageSize: 100 });
  const [draftAppointmentFilters, setDraftAppointmentFilters] =
    useState<AppointmentFilters>({ pageSize: 100 });
  const [appointmentToCancel, setAppointmentToCancel] =
    useState<AppointmentAnalysis | null>(null);

  const statusQuery = useQuery({
    queryKey: ["calendar-status", clinicId],
    queryFn: () => getCalendarStatus(clinicId as string),
    enabled,
  });
  const calendarsQuery = useQuery({
    queryKey: ["calendars", clinicId],
    queryFn: () => listCalendars(clinicId as string),
    enabled: enabled && Boolean(statusQuery.data?.connected),
  });
  const workersQuery = useQuery({
    queryKey: ["workers", clinicId],
    queryFn: () => listWorkers(clinicId as string),
    enabled,
  });
  const servicesQuery = useQuery({
    queryKey: ["services", clinicId],
    queryFn: () => listServices(clinicId as string),
    enabled,
  });
  const appointmentsQuery = useQuery({
    queryKey: ["appointments", clinicId, appointmentFilters],
    queryFn: () =>
      listAppointments(clinicId as string, appointmentFilters),
    enabled,
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["workers", clinicId] }),
      queryClient.invalidateQueries({ queryKey: ["calendar-status", clinicId] }),
      queryClient.invalidateQueries({ queryKey: ["calendars", clinicId] }),
    ]);
  };
  const createMutation = useMutation({
    mutationFn: ({
      workerId,
      workerName,
      colorId,
    }: {
      workerId: string;
      workerName: string;
      colorId?: string;
    }) =>
      createWorkerCalendar(clinicId as string, workerId, {
        summary: `Clínica - ${workerName}`,
        color_id: colorId,
      }),
    onSuccess: async () => {
      await refresh();
      toast.success("Calendario creado y enlazado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const linkMutation = useMutation({
    mutationFn: ({
      workerId,
      calendarId,
      colorId,
    }: {
      workerId: string;
      calendarId: string;
      colorId?: string;
    }) =>
      linkWorkerCalendar(clinicId as string, workerId, {
        calendar_id: calendarId,
        color_id: colorId,
      }),
    onSuccess: async () => {
      await refresh();
      toast.success("Calendario enlazado");
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const freeBusyMutation = useMutation({
    mutationFn: (workerId: string) => {
      const timeMin = new Date();
      const timeMax = new Date(timeMin.getTime() + 7 * 24 * 60 * 60 * 1000);
      return testWorkerFreeBusy(clinicId as string, workerId, {
        time_min: timeMin.toISOString(),
        time_max: timeMax.toISOString(),
      });
    },
    onSuccess: (result) =>
      toast.success(
        `FreeBusy correcto: ${result.busy_ranges.length} tramo(s) ocupado(s) en 7 días.`,
      ),
    onError: (error: Error) => toast.error(error.message),
  });
  const cancelMutation = useMutation({
    mutationFn: (appointmentId: string) =>
      cancelAppointment(clinicId as string, appointmentId),
    onSuccess: async () => {
      setAppointmentToCancel(null);
      await queryClient.invalidateQueries({
        queryKey: ["appointments", clinicId],
      });
      toast.success("Cita cancelada");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const updateSelection = (
    workerId: string,
    values: Partial<WorkerCalendarSelection>,
  ) => {
    setSelections((current) => ({
      ...current,
      [workerId]: {
        calendarId: current[workerId]?.calendarId ?? "",
        colorId: current[workerId]?.colorId ?? "",
        ...values,
      },
    }));
  };

  if (statusQuery.isLoading) return <LoadingState rows={5} />;
  if (statusQuery.error) return <ErrorState error={statusQuery.error} />;
  const status = statusQuery.data;
  const appointmentColumns: Array<DataTableColumn<AppointmentAnalysis>> = [
    {
      key: "date",
      header: "Fecha y hora",
      cell: (appointment) => formatDateTime(appointment.start_at),
    },
    {
      key: "patient",
      header: "Paciente",
      cell: (appointment) => (
        <div>
          <p className="font-semibold text-[#27334a]">
            {appointment.patient_name}
          </p>
          <p className="mt-1 text-xs text-[#7b8799]">
            {appointment.patient_phone}
          </p>
        </div>
      ),
    },
    {
      key: "worker",
      header: "Trabajador",
      cell: (appointment) => appointment.worker_name,
    },
    {
      key: "service",
      header: "Servicio",
      cell: (appointment) => appointment.service_name || "—",
    },
    {
      key: "status",
      header: "Estado",
      cell: (appointment) => (
        <StatusBadge
          status={
            appointment.status === "confirmed"
              ? "success"
              : appointment.status === "cancelled"
                ? "neutral"
                : appointment.status === "failed"
                  ? "danger"
                  : "warning"
          }
        >
          {appointment.status === "confirmed"
            ? "Confirmada"
            : appointment.status === "cancelled"
              ? "Cancelada"
              : appointment.status === "failed"
                ? "Fallida"
                : "Pendiente"}
        </StatusBadge>
      ),
    },
    {
      key: "source",
      header: "Origen",
      cell: (appointment) =>
        appointment.source === "voice_bot" ? "Asistente de voz" : "Manual",
    },
    {
      key: "google",
      header: "Google event",
      cell: (appointment) => (
        <p className="max-w-[180px] truncate font-mono text-xs">
          {appointment.google_event_id}
        </p>
      ),
    },
    {
      key: "actions",
      header: "",
      cell: (appointment) => (
        <Button
          size="sm"
          variant="outline"
          disabled={appointment.status === "cancelled"}
          onClick={() => setAppointmentToCancel(appointment)}
        >
          Cancelar
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-7">
      <PageHeader
        title="Google Calendar"
        description="OAuth, calendarios secundarios, colores y diagnóstico FreeBusy."
        actions={
          clinicId && !status?.connected ? (
            <Button asChild>
              <a
                href={`${apiConfig.baseUrl}/auth/google/start?clinic_id=${clinicId}`}
                target="_blank"
                rel="noreferrer"
              >
                <Link2 className="size-4" />
                Conectar Google Calendar
              </a>
            </Button>
          ) : (
            <Button
              variant="outline"
              onClick={() => void refresh()}
              disabled={!status?.connected}
            >
              <RefreshCw className="size-4" />
              Actualizar
            </Button>
          )
        }
      />

      <div className="grid gap-5 md:grid-cols-3">
        <Card className="p-5 md:col-span-2">
          <div className="flex items-start gap-4">
            <div
              className={`grid size-11 place-items-center rounded-xl ${
                status?.connected
                  ? "bg-[#e9f8ef] text-[#24804a]"
                  : "bg-[#fff4df] text-[#ad7111]"
              }`}
            >
              {status?.connected ? (
                <CheckCircle2 className="size-5" />
              ) : (
                <Unlink className="size-5" />
              )}
            </div>
            <div>
              <h3 className="font-semibold text-[#27334a]">
                {status?.connected
                  ? "Google Calendar conectado"
                  : "Google Calendar pendiente"}
              </h3>
              <p className="mt-1 text-sm text-[#758197]">
                {status?.account_email ||
                  "Autoriza la cuenta Google única de esta clínica."}
              </p>
              {status?.needs_reauthorization ? (
                <p className="mt-2 text-sm font-medium text-[#ad7111]">
                  El token necesita autorización de nuevo.
                </p>
              ) : null}
            </div>
          </div>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-medium text-[#748096]">Calendarios enlazados</p>
          <p className="mt-2 text-3xl font-bold text-[#263249]">
            {status?.workers_linked ?? 0}
            <span className="text-base font-medium text-[#8993a4]">
              {" "}/ {status?.workers_total ?? 0}
            </span>
          </p>
        </Card>
      </div>

      {status?.connected ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Calendarios disponibles</CardTitle>
              <CardDescription>
                Calendarios escribibles y colores visibles para la cuenta OAuth.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {calendarsQuery.isLoading ? <LoadingState rows={3} /> : null}
              {calendarsQuery.error ? <ErrorState error={calendarsQuery.error} /> : null}
              <div className="grid gap-3 md:grid-cols-2">
                {calendarsQuery.data?.calendars.map((calendar) => (
                  <div
                    key={calendar.id}
                    className="flex items-center justify-between rounded-xl border border-[#e7eaf0] p-4"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span
                        className="size-3 shrink-0 rounded-full"
                        style={{ backgroundColor: calendar.background_color || "#315efb" }}
                      />
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-[#27334a]">
                          {calendar.summary}
                        </p>
                        <p className="mt-1 truncate text-xs text-[#7c8799]">
                          {calendar.id}
                        </p>
                      </div>
                    </div>
                    {calendar.primary ? (
                      <StatusBadge status="info">Principal</StatusBadge>
                    ) : null}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Calendario por trabajador</CardTitle>
              <CardDescription>
                Crea uno secundario o enlaza uno existente. Cada trabajador reserva de forma independiente.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {workersQuery.isLoading ? <LoadingState rows={4} /> : null}
              {workersQuery.error ? <ErrorState error={workersQuery.error} /> : null}
              {workersQuery.data?.items.map((worker) => {
                const selection = selections[worker.id] ?? {
                  calendarId: worker.calendar_id ?? "",
                  colorId: worker.color_id ?? "",
                };
                return (
                  <div
                    key={worker.id}
                    className="rounded-xl border border-[#e5e9f0] p-4"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-[#27334a]">{worker.name}</p>
                          <StatusBadge status={worker.calendar_id ? "success" : "warning"}>
                            {worker.calendar_id ? "Calendario conectado" : "Sin calendario"}
                          </StatusBadge>
                          {!worker.is_active ? (
                            <StatusBadge status="neutral">Inactivo</StatusBadge>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-[#7d8899]">
                          {worker.calendar_id || "Sin Calendar ID"}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {!worker.calendar_id ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={createMutation.isPending}
                            onClick={() =>
                              createMutation.mutate({
                                workerId: worker.id,
                                workerName: worker.name,
                                colorId: selection.colorId || undefined,
                              })
                            }
                          >
                            <CalendarCheck2 className="size-4" />
                            Crear calendario
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={!worker.calendar_id || freeBusyMutation.isPending}
                          onClick={() => freeBusyMutation.mutate(worker.id)}
                        >
                          Probar FreeBusy
                        </Button>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-[1fr_180px_auto] md:items-end">
                      <div>
                        <Label htmlFor={`calendar-${worker.id}`}>Calendario existente</Label>
                        <Select
                          id={`calendar-${worker.id}`}
                          className="mt-1.5"
                          value={selection.calendarId}
                          onChange={(event) =>
                            updateSelection(worker.id, { calendarId: event.target.value })
                          }
                        >
                          <option value="">Selecciona calendario</option>
                          {calendarsQuery.data?.calendars.map((calendar) => (
                            <option key={calendar.id} value={calendar.id}>
                              {calendar.summary}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div>
                        <Label htmlFor={`color-${worker.id}`}>Color de evento</Label>
                        <Select
                          id={`color-${worker.id}`}
                          className="mt-1.5"
                          value={selection.colorId}
                          onChange={(event) =>
                            updateSelection(worker.id, { colorId: event.target.value })
                          }
                        >
                          <option value="">Color por defecto</option>
                          {calendarsQuery.data?.event_colors.map((color) => (
                            <option key={color.id} value={color.id}>
                              Color {color.id} · {color.background}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <Button
                        disabled={!selection.calendarId || linkMutation.isPending}
                        onClick={() =>
                          linkMutation.mutate({
                            workerId: worker.id,
                            calendarId: selection.calendarId,
                            colorId: selection.colorId || undefined,
                          })
                        }
                      >
                        Enlazar y guardar
                      </Button>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </>
      ) : (
        <Card className="border-dashed p-8 text-center">
          <Unlink className="mx-auto size-8 text-[#9aa4b4]" />
          <p className="mt-3 font-semibold text-[#27334a]">
            Conecta Google antes de gestionar calendarios.
          </p>
          <p className="mt-1 text-sm text-[#758197]">
            La aplicación guardará los tokens OAuth cifrados en el backend.
          </p>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Citas</CardTitle>
          <CardDescription>
            Reservas creadas por el asistente o desde el panel.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <form
            className="grid gap-3 md:grid-cols-2 xl:grid-cols-5"
            onSubmit={(event) => {
              event.preventDefault();
              setAppointmentFilters({ ...draftAppointmentFilters });
            }}
          >
            <div>
              <Label htmlFor="appointment-from">Desde</Label>
              <Input
                id="appointment-from"
                type="date"
                className="mt-1.5"
                value={draftAppointmentFilters.dateFrom ?? ""}
                onChange={(event) =>
                  setDraftAppointmentFilters((current) => ({
                    ...current,
                    dateFrom: event.target.value,
                  }))
                }
              />
            </div>
            <div>
              <Label htmlFor="appointment-to">Hasta</Label>
              <Input
                id="appointment-to"
                type="date"
                className="mt-1.5"
                value={draftAppointmentFilters.dateTo ?? ""}
                onChange={(event) =>
                  setDraftAppointmentFilters((current) => ({
                    ...current,
                    dateTo: event.target.value,
                  }))
                }
              />
            </div>
            <div>
              <Label htmlFor="appointment-status">Estado</Label>
              <Select
                id="appointment-status"
                className="mt-1.5"
                value={draftAppointmentFilters.status ?? ""}
                onChange={(event) =>
                  setDraftAppointmentFilters((current) => ({
                    ...current,
                    status: event.target
                      .value as AppointmentFilters["status"],
                  }))
                }
              >
                <option value="">Todos</option>
                <option value="pending">Pendiente</option>
                <option value="confirmed">Confirmada</option>
                <option value="cancelled">Cancelada</option>
                <option value="failed">Fallida</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="appointment-worker">Trabajador</Label>
              <Select
                id="appointment-worker"
                className="mt-1.5"
                value={draftAppointmentFilters.workerId ?? ""}
                onChange={(event) =>
                  setDraftAppointmentFilters((current) => ({
                    ...current,
                    workerId: event.target.value,
                  }))
                }
              >
                <option value="">Todos</option>
                {workersQuery.data?.items.map((worker) => (
                  <option key={worker.id} value={worker.id}>
                    {worker.name}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="appointment-service">Servicio</Label>
              <Select
                id="appointment-service"
                className="mt-1.5"
                value={draftAppointmentFilters.serviceId ?? ""}
                onChange={(event) =>
                  setDraftAppointmentFilters((current) => ({
                    ...current,
                    serviceId: event.target.value,
                  }))
                }
              >
                <option value="">Todos</option>
                {servicesQuery.data?.items.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.public_name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex gap-2 md:col-span-2 xl:col-span-5">
              <Button type="submit">
                <Search className="size-4" />
                Filtrar citas
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  const empty = { pageSize: 100 };
                  setDraftAppointmentFilters(empty);
                  setAppointmentFilters(empty);
                }}
              >
                Limpiar
              </Button>
            </div>
          </form>

          {appointmentsQuery.isLoading ? <LoadingState rows={5} /> : null}
          {appointmentsQuery.error ? (
            <ErrorState error={appointmentsQuery.error} />
          ) : null}
          {appointmentsQuery.data ? (
            <DataTable
              columns={appointmentColumns}
              rows={appointmentsQuery.data.items}
              rowKey={(appointment) => appointment.id}
            />
          ) : null}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={appointmentToCancel !== null}
        onOpenChange={(open) => {
          if (!open) setAppointmentToCancel(null);
        }}
        title="Cancelar cita"
        description={
          appointmentToCancel
            ? `Se cancelará la cita de ${appointmentToCancel.patient_name}. No se borrará de la base de datos.`
            : ""
        }
        confirmLabel="Cancelar cita"
        isPending={cancelMutation.isPending}
        onConfirm={() => {
          if (appointmentToCancel) {
            cancelMutation.mutate(appointmentToCancel.id);
          }
        }}
      />
    </div>
  );
}
