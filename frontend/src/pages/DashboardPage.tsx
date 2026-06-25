import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CalendarCheck2,
  CalendarClock,
  CheckCircle2,
  CircleX,
  Phone,
  PhoneCall,
  Stethoscope,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import {
  getClinicDashboard,
  getSetupStatus,
} from "@/api/dashboard";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { MetricCard } from "@/components/common/MetricCard";
import { PageHeader } from "@/components/common/PageHeader";
import { SetupChecklist } from "@/components/common/SetupChecklist";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useActiveClinic } from "@/hooks/useActiveClinic";
import {
  callOutcomeLabels,
  callOutcomeTone,
  callStatusLabels,
  callStatusTone,
} from "@/lib/calls";
import { formatDateTime } from "@/lib/format";

export function DashboardPage() {
  const { activeClinic, activeClinicId, isLoading: clinicLoading } =
    useActiveClinic();
  const enabled = Boolean(activeClinicId);
  const dashboardQuery = useQuery({
    queryKey: ["dashboard", activeClinicId],
    queryFn: () => getClinicDashboard(activeClinicId as string),
    enabled,
    refetchInterval: 60_000,
  });
  const setupQuery = useQuery({
    queryKey: ["setup-status", activeClinicId],
    queryFn: () => getSetupStatus(activeClinicId as string),
    enabled,
  });

  if (clinicLoading) return <LoadingState rows={8} />;
  if (!activeClinicId || !activeClinic) {
    return (
      <EmptyState
        icon={Stethoscope}
        title="Crea tu primera clínica"
        description="El dashboard se activará cuando exista una clínica seleccionada."
        action={
          <Button asChild>
            <Link to="/clinics">Gestionar clínicas</Link>
          </Button>
        }
      />
    );
  }
  const firstError = dashboardQuery.error ?? setupQuery.error;
  if (firstError) return <ErrorState error={firstError} />;
  if (!dashboardQuery.data || !setupQuery.data) {
    return <LoadingState rows={8} />;
  }

  const dashboard = dashboardQuery.data;
  const setup = setupQuery.data;

  return (
    <div className="space-y-7">
      <PageHeader
        title={activeClinic.name}
        description="Estado operativo y pasos pendientes para publicar la clínica."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to={`/clinics/${activeClinicId}`}>Configurar clínica</Link>
            </Button>
            <Button asChild>
              <Link to={`/clinics/${activeClinicId}/test`}>
                Probar asistente
              </Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={dashboard.configuration_complete ? CheckCircle2 : CircleX}
          label="Configuración completa"
          value={dashboard.configuration_complete ? "Sí" : "No"}
          hint={
            dashboard.configuration_complete
              ? "Lista para producción"
              : `${setup.blocking_errors.length} bloqueo(s)`
          }
          accent={dashboard.configuration_complete ? "green" : "amber"}
        />
        <MetricCard
          icon={CalendarCheck2}
          label="Google Calendar"
          value={dashboard.google_calendar_connected ? "Sí" : "No"}
          hint={
            dashboard.google_calendar_connected
              ? "OAuth conectado"
              : "Conexión pendiente"
          }
          accent={dashboard.google_calendar_connected ? "green" : "amber"}
        />
        <MetricCard
          icon={Phone}
          label="Número configurado"
          value={dashboard.phone_number_configured ? "Sí" : "No"}
          hint="Número activo con destino SIP"
          accent={dashboard.phone_number_configured ? "green" : "amber"}
        />
        <MetricCard
          icon={Bot}
          label="Asistente activo"
          value={dashboard.assistant_active ? "Sí" : "No"}
          hint="Configuración efectiva"
          accent={dashboard.assistant_active ? "green" : "amber"}
        />
        <MetricCard
          icon={Users}
          label="Trabajadores activos"
          value={dashboard.active_workers}
          accent="violet"
        />
        <MetricCard
          icon={Stethoscope}
          label="Servicios reservables"
          value={dashboard.bookable_services}
          accent="green"
        />
        <MetricCard
          icon={PhoneCall}
          label="Llamadas últimas 24h"
          value={dashboard.calls_last_24h}
        />
        <MetricCard
          icon={CalendarClock}
          label="Citas próximas"
          value={dashboard.upcoming_appointments}
          hint="Siguientes 30 días"
          accent="violet"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader>
            <CardTitle>Salud reciente</CardTitle>
            <CardDescription>
              Errores de llamadas y eventos técnicos en 24 horas.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              className={`flex items-center gap-4 rounded-xl p-5 ${
                dashboard.recent_errors
                  ? "bg-[#fff3f4] text-[#9e3945]"
                  : "bg-[#eef9f2] text-[#28764a]"
              }`}
            >
              <AlertTriangle className="size-7" />
              <div>
                <p className="text-3xl font-bold">{dashboard.recent_errors}</p>
                <p className="mt-1 text-sm font-medium">Errores recientes</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Última llamada recibida</CardTitle>
              <CardDescription>
                Excluye simulaciones y pruebas del navegador.
              </CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to={`/clinics/${activeClinicId}/conversations`}>
                Ver llamadas
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {dashboard.last_call ? (
              <div className="rounded-xl border border-[#e5e9ef] p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-[#27334a]">
                      {dashboard.last_call.caller_phone}
                    </p>
                    <p className="mt-1 text-sm text-[#748095]">
                      A {dashboard.last_call.called_number} ·{" "}
                      {formatDateTime(dashboard.last_call.started_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge
                      status={callStatusTone(dashboard.last_call.status)}
                    >
                      {callStatusLabels[dashboard.last_call.status]}
                    </StatusBadge>
                    {dashboard.last_call.outcome ? (
                      <StatusBadge
                        status={callOutcomeTone(dashboard.last_call.outcome)}
                      >
                        {callOutcomeLabels[dashboard.last_call.outcome]}
                      </StatusBadge>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-[#7b8799]">
                Todavía no hay llamadas reales.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <SetupChecklist status={setup} />

      {setup.warnings.length ? (
        <Card className="border-[#eed9b4] bg-[#fffbf2]">
          <CardContent className="pt-5">
            <p className="font-semibold text-[#8c641d]">Avisos no bloqueantes</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[#80672f]">
              {setup.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
