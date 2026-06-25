import { useQuery } from "@tanstack/react-query";
import { Eye, MessageSquareText, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { listCalls, type CallFilters } from "@/api/calls";
import { listServices } from "@/api/services";
import { listWorkers } from "@/api/workers";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { DataTable, type DataTableColumn } from "@/components/tables/DataTable";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import {
  callOutcomeLabels,
  callOutcomeTone,
  callStatusLabels,
  callStatusTone,
  formatDuration,
} from "@/lib/calls";
import { formatDateTime } from "@/lib/format";
import type { CallAnalysis } from "@/schemas/domain";

const emptyFilters: CallFilters = {
  pageSize: 100,
  dateFrom: "",
  dateTo: "",
  status: "",
  outcome: "",
  phone: "",
  workerId: "",
  serviceId: "",
};

export function ConversationsPage() {
  const clinicId = useClinicRoute();
  const [draftFilters, setDraftFilters] = useState<CallFilters>(emptyFilters);
  const [filters, setFilters] = useState<CallFilters>(emptyFilters);
  const callsQuery = useQuery({
    queryKey: ["calls", clinicId, filters],
    queryFn: () => listCalls(clinicId as string, filters),
    enabled: Boolean(clinicId),
  });
  const workersQuery = useQuery({
    queryKey: ["workers", clinicId],
    queryFn: () => listWorkers(clinicId as string),
    enabled: Boolean(clinicId),
  });
  const servicesQuery = useQuery({
    queryKey: ["services", clinicId],
    queryFn: () => listServices(clinicId as string),
    enabled: Boolean(clinicId),
  });

  const columns: Array<DataTableColumn<CallAnalysis>> = [
    {
      key: "date",
      header: "Fecha y hora",
      cell: (call) => formatDateTime(call.started_at),
    },
    {
      key: "phones",
      header: "Teléfonos",
      cell: (call) => (
        <div>
          <p className="font-semibold text-[#27334a]">{call.caller_phone}</p>
          <p className="mt-1 text-xs text-[#7b8799]">A {call.called_number}</p>
        </div>
      ),
    },
    {
      key: "status",
      header: "Estado",
      cell: (call) => (
        <StatusBadge status={callStatusTone(call.status)}>
          {callStatusLabels[call.status]}
        </StatusBadge>
      ),
    },
    {
      key: "outcome",
      header: "Resultado",
      cell: (call) =>
        call.outcome ? (
          <StatusBadge status={callOutcomeTone(call.outcome)}>
            {callOutcomeLabels[call.outcome]}
          </StatusBadge>
        ) : (
          "—"
        ),
    },
    {
      key: "booking",
      header: "Cita",
      cell: (call) =>
        call.appointment ? (
          <div>
            <StatusBadge status="success">Cita creada</StatusBadge>
            <p className="mt-1 text-xs text-[#6f7b8f]">
              {call.appointment.worker_name}
              {call.appointment.service_name
                ? ` · ${call.appointment.service_name}`
                : ""}
            </p>
          </div>
        ) : (
          <StatusBadge status="neutral">Sin cita</StatusBadge>
        ),
    },
    {
      key: "duration",
      header: "Duración",
      cell: (call) => formatDuration(call.duration_seconds),
    },
    {
      key: "transcript",
      header: "Transcripción",
      cell: (call) => (
        <StatusBadge status={call.transcript_text ? "info" : "neutral"}>
          {call.transcript_text ? "Disponible" : "No"}
        </StatusBadge>
      ),
    },
    {
      key: "summary",
      header: "Resumen",
      cell: (call) => (
        <p className="max-w-[260px] truncate">{call.summary_text || "—"}</p>
      ),
    },
    {
      key: "actions",
      header: "",
      cell: (call) => (
        <Button asChild size="sm" variant="outline">
          <Link to={`/clinics/${clinicId}/conversations/${call.id}`}>
            <Eye className="size-4" />
            Ver
          </Link>
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-7">
      <PageHeader
        title="Conversaciones"
        description="Llamadas, resultados, citas y datos técnicos del asistente."
      />

      <Card className="p-5">
        <form
          className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            setFilters({ ...draftFilters });
          }}
        >
          <div>
            <Label htmlFor="call-date-from">Desde</Label>
            <Input
              id="call-date-from"
              type="date"
              className="mt-1.5"
              value={draftFilters.dateFrom}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  dateFrom: event.target.value,
                }))
              }
            />
          </div>
          <div>
            <Label htmlFor="call-date-to">Hasta</Label>
            <Input
              id="call-date-to"
              type="date"
              className="mt-1.5"
              value={draftFilters.dateTo}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  dateTo: event.target.value,
                }))
              }
            />
          </div>
          <div>
            <Label htmlFor="call-status">Estado</Label>
            <Select
              id="call-status"
              className="mt-1.5"
              value={draftFilters.status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  status: event.target.value as CallFilters["status"],
                }))
              }
            >
              <option value="">Todos</option>
              <option value="incoming">Entrante</option>
              <option value="active">Activa</option>
              <option value="completed">Completada</option>
              <option value="failed">Fallida</option>
              <option value="transferred">Transferida</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="call-outcome">Resultado</Label>
            <Select
              id="call-outcome"
              className="mt-1.5"
              value={draftFilters.outcome}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  outcome: event.target.value as CallFilters["outcome"],
                }))
              }
            >
              <option value="">Todos</option>
              <option value="appointment_created">Cita creada</option>
              <option value="cancelled">Cancelada</option>
              <option value="transferred">Transferida</option>
              <option value="no_action">Sin acción</option>
              <option value="failed">Fallida</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="call-phone">Teléfono</Label>
            <Input
              id="call-phone"
              className="mt-1.5"
              placeholder="+34..."
              value={draftFilters.phone}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  phone: event.target.value,
                }))
              }
            />
          </div>
          <div>
            <Label htmlFor="call-worker">Trabajador</Label>
            <Select
              id="call-worker"
              className="mt-1.5"
              value={draftFilters.workerId}
              onChange={(event) =>
                setDraftFilters((current) => ({
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
            <Label htmlFor="call-service">Servicio</Label>
            <Select
              id="call-service"
              className="mt-1.5"
              value={draftFilters.serviceId}
              onChange={(event) =>
                setDraftFilters((current) => ({
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
          <div className="flex items-end gap-2">
            <Button type="submit">
              <Search className="size-4" />
              Filtrar
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraftFilters(emptyFilters);
                setFilters(emptyFilters);
              }}
            >
              Limpiar
            </Button>
          </div>
        </form>
      </Card>

      {callsQuery.isLoading ? <LoadingState rows={7} /> : null}
      {callsQuery.error ? <ErrorState error={callsQuery.error} /> : null}
      {callsQuery.data?.items.length ? (
        <DataTable
          columns={columns}
          rows={callsQuery.data.items}
          rowKey={(row) => row.id}
        />
      ) : !callsQuery.isLoading && !callsQuery.error ? (
        <EmptyState
          icon={MessageSquareText}
          title="Sin conversaciones"
          description="No hay llamadas que coincidan con los filtros."
        />
      ) : null}
    </div>
  );
}
