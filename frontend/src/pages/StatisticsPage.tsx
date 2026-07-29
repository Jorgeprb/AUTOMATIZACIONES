import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Euro, PhoneCall, TrendingUp } from "lucide-react";
import { useState } from "react";

import { getAnalytics, type AnalyticsFilters } from "@/api/enterprise";
import { listServices } from "@/api/services";
import { listWorkers } from "@/api/workers";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { MetricCard } from "@/components/common/MetricCard";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import { BarChart, DonutChart, FunnelChart, Heatmap, LineChart } from "@/lib/charts";

const initialFilters: AnalyticsFilters = { period: "30d" };

export function StatisticsPage() {
  const clinicId = useClinicRoute();
  const [filters, setFilters] = useState<AnalyticsFilters>(initialFilters);
  const analyticsQuery = useQuery({
    queryKey: ["analytics", clinicId, filters],
    queryFn: () => getAnalytics(clinicId as string, filters),
    enabled: Boolean(clinicId),
  });
  const workersQuery = useQuery({
    queryKey: ["workers", clinicId, "analytics"],
    queryFn: () => listWorkers(clinicId as string, true),
    enabled: Boolean(clinicId),
  });
  const servicesQuery = useQuery({
    queryKey: ["services", clinicId, "analytics"],
    queryFn: () => listServices(clinicId as string, true),
    enabled: Boolean(clinicId),
  });

  if (analyticsQuery.isLoading) return <LoadingState rows={8} />;
  if (analyticsQuery.isError || !analyticsQuery.data)
    return (
      <ErrorState
        error={analyticsQuery.error ?? new Error("Sin datos")}
        onRetry={() => analyticsQuery.refetch()}
      />
    );

  const analytics = analyticsQuery.data;
  const workers = workersQuery.data?.items ?? [];
  const services = servicesQuery.data?.items ?? [];
  return (
    <div className="space-y-7">
      <PageHeader
        title="Estadísticas"
        description="Citas, llamadas, conversión e ingresos calculados en la zona horaria de la clínica."
      />
      <Card>
        <CardContent className="grid gap-4 pt-5 sm:grid-cols-2 xl:grid-cols-4">
          <FilterField label="Periodo">
            <Select
              value={filters.period}
              onChange={(event) =>
                setFilters({
                  ...filters,
                  period: event.target.value,
                  date_from: event.target.value === "custom" ? filters.date_from : undefined,
                  date_to: event.target.value === "custom" ? filters.date_to : undefined,
                })
              }
            >
              <option value="today">Hoy</option>
              <option value="7d">Últimos 7 días</option>
              <option value="30d">Últimos 30 días</option>
              <option value="month">Mes actual</option>
              <option value="custom">Rango personalizado</option>
            </Select>
          </FilterField>
          <FilterField label="Trabajador">
            <Select value={filters.worker_id ?? ""} onChange={(event) => setFilters({ ...filters, worker_id: event.target.value || undefined })}>
              <option value="">Todos</option>
              {workers.map((worker) => <option key={worker.id} value={worker.id}>{worker.name}</option>)}
            </Select>
          </FilterField>
          <FilterField label="Servicio">
            <Select value={filters.service_id ?? ""} onChange={(event) => setFilters({ ...filters, service_id: event.target.value || undefined })}>
              <option value="">Todos</option>
              {services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
            </Select>
          </FilterField>
          <FilterField label="Estado de cita">
            <Select value={filters.appointment_status ?? ""} onChange={(event) => setFilters({ ...filters, appointment_status: event.target.value || undefined })}>
              <option value="">Todos</option>
              <option value="scheduled">Programada</option>
              <option value="completed">Completada</option>
              <option value="cancelled">Cancelada</option>
              <option value="no_show">No presentado</option>
              <option value="rescheduled">Modificada</option>
            </Select>
          </FilterField>
          <FilterField label="Número de teléfono">
            <Input value={filters.phone_number ?? ""} onChange={(event) => setFilters({ ...filters, phone_number: event.target.value || undefined })} placeholder="Buscar llamadas o citas" />
          </FilterField>
          {filters.period === "custom" && <>
            <FilterField label="Desde"><Input type="date" value={dateInput(filters.date_from)} onChange={(event) => setFilters({ ...filters, date_from: event.target.value ? `${event.target.value}T00:00:00` : undefined })} /></FilterField>
            <FilterField label="Hasta"><Input type="date" value={dateInput(filters.date_to)} onChange={(event) => setFilters({ ...filters, date_to: event.target.value ? `${event.target.value}T23:59:59` : undefined })} /></FilterField>
          </>}
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={CalendarCheck} label="Citas" value={analytics.appointments_created} />
        <MetricCard icon={TrendingUp} label="Conversión" value={`${Math.round(analytics.call_to_booking_conversion * 100)}%`} accent="green" />
        <MetricCard icon={PhoneCall} label="Llamadas" value={analytics.calls_answered} accent="violet" />
        <MetricCard icon={Euro} label="Ingresos estimados" value={`${(analytics.estimated_revenue_minor / 100).toFixed(2)} €`} accent="amber" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SmallMetric label="Citas canceladas" value={analytics.appointments_cancelled} />
        <SmallMetric label="Citas completadas" value={analytics.appointments_completed} />
        <SmallMetric label="No presentados" value={analytics.appointments_no_show} />
        <SmallMetric label="Duración media de llamada" value={`${Math.round(analytics.average_call_duration_seconds)} s`} />
        <SmallMetric label="Clientes nuevos" value={analytics.new_customers} />
        <SmallMetric label="Clientes recurrentes" value={analytics.returning_customers} />
        <SmallMetric label="Tasa de cancelación" value={`${Math.round(analytics.cancellation_rate * 100)}%`} />
        <SmallMetric label="Llamadas con error" value={analytics.calls_failed} />
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <ChartCard title="Evolución de citas"><LineChart data={analytics.timeline} /></ChartCard>
        <ChartCard title="Citas por servicio"><BarChart data={analytics.appointments_by_service} /></ChartCard>
        <ChartCard title="Citas por profesional"><BarChart data={analytics.appointments_by_worker} /></ChartCard>
        <ChartCard title="Distribución horaria"><BarChart data={analytics.appointments_by_hour} /></ChartCard>
        <ChartCard title="Días de la semana"><BarChart data={analytics.appointments_by_weekday} /></ChartCard>
        <ChartCard title="Estados de cita"><DonutChart data={analytics.appointment_statuses} centerLabel="Estados" /></ChartCard>
        <ChartCard title="Sentimiento de llamadas"><DonutChart data={analytics.sentiments} centerLabel="Sentimiento" /></ChartCard>
        <ChartCard title="Embudo llamadas → citas"><FunnelChart data={[{ label: "Llamadas", value: analytics.calls_answered }, { label: "Citas", value: analytics.appointments_created }]} /></ChartCard>
      </div>
      <ChartCard title="Mapa de calor por día y hora"><Heatmap data={analytics.heatmap.map((item) => ({ day: String(item.day), hour: String(item.hour), value: Number(item.value) }))} /></ChartCard>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>;
}
function SmallMetric({ label, value }: { label:string; value:string|number }) {
  return <Card><CardContent className="pt-5"><p className="text-sm text-[#6f7b8f]">{label}</p><p className="mt-1 text-2xl font-semibold text-[#172033]">{value}</p></CardContent></Card>;
}
function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card><CardHeader><CardTitle>{title}</CardTitle></CardHeader><CardContent>{children}</CardContent></Card>;
}
function dateInput(value?:string) { return value ? value.slice(0,10) : ""; }
