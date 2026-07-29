import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CalendarCheck2,
  CalendarClock,
  CheckCircle2,
  CircleX,
  Clock3,
  Phone,
  PhoneCall,
  Settings,
  ShoppingCart,
  Stethoscope,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";

import { getClinicDashboard, getSetupStatus } from "@/api/dashboard";
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
import { useCommercialAccess } from "@/hooks/useCommercialAccess";
import {
  callOutcomeLabels,
  callOutcomeTone,
  callStatusLabels,
  callStatusTone,
} from "@/lib/calls";
import { formatDateTime } from "@/lib/format";
import { isClientPortal } from "@/lib/portal";

function WelcomeDashboard({
  clinicId,
  clinicName,
  demoPhone,
}: {
  clinicId: string | null;
  clinicName?: string;
  demoPhone: string;
}) {
  const purchasePath = clinicId ? `/clinics/${clinicId}/purchases` : "/clinics";
  return (
    <div className="space-y-7">
      <PageHeader
        title={clinicName ? `Bienvenido a ${clinicName}` : "Bienvenido a Autogal"}
        description="Tu portal está preparado. El primer paso es contratar un número Autogal."
      />
      <Card className="overflow-hidden border-[#cbd7ff] bg-gradient-to-br from-[#f4f7ff] to-white">
        <CardContent className="grid gap-7 p-6 lg:grid-cols-[1.25fr_0.75fr] lg:p-8">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-[#e7edff] px-3 py-1 text-xs font-bold text-[#3152c8]">
              <Phone className="size-3.5" /> Primer paso
            </div>
            <h2 className="mt-4 text-2xl font-bold text-[#202d46]">
              Compra un número de teléfono Autogal
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#647187]">
              Es un número VoIP fijo que atenderá el asistente. Puedes publicar este número directamente o redirigir hacia él las llamadas de tu número habitual, sin cambiar el teléfono que ya conocen tus clientes.
            </p>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[#647187]">
              Después del pago tendrás acceso permanente a la configuración del portal. La entrega y activación del número puede tardar hasta 24 horas.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button asChild>
                <Link to={purchasePath}>
                  <ShoppingCart className="size-4" /> Comprar un número
                </Link>
              </Button>
              {!clinicId ? (
                <Button asChild variant="outline">
                  <Link to="/clinics">Crear primero una clínica</Link>
                </Button>
              ) : null}
            </div>
          </div>
          <div className="rounded-2xl border border-[#dbe3ff] bg-white p-5 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#7a87a0]">
              Pruébalo antes de decidir
            </p>
            <p className="mt-3 text-sm leading-6 text-[#627087]">
              Llama al número de demostración y comprueba cómo responde el bot antes de contratar.
            </p>
            <p className="mt-5 text-xl font-bold text-[#263550]">{demoPhone}</p>
            <Button asChild className="mt-4 w-full" variant="outline">
              <a href={`tel:${demoPhone.replace(/\s+/g, "")}`}>
                <PhoneCall className="size-4" /> Llamar a la prueba
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function DashboardPage() {
  const { activeClinic, activeClinicId, isLoading: clinicLoading } =
    useActiveClinic();
  const access = useCommercialAccess();
  const enabled = Boolean(activeClinicId) && (!isClientPortal || access.unlocked);
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

  if (clinicLoading || access.isResolving) return <LoadingState rows={8} />;
  const demoPhone = access.summary?.demo_phone_number || "+34 881 17 08 37";
  if (!activeClinicId || !activeClinic) {
    return isClientPortal ? (
      <WelcomeDashboard clinicId={null} demoPhone={demoPhone} />
    ) : (
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
  if (isClientPortal && !access.unlocked) {
    return (
      <WelcomeDashboard
        clinicId={activeClinicId}
        clinicName={activeClinic.name}
        demoPhone={demoPhone}
      />
    );
  }

  const firstError = dashboardQuery.error ?? setupQuery.error;
  if (firstError) return <ErrorState error={firstError} />;
  if (!dashboardQuery.data || !setupQuery.data) return <LoadingState rows={8} />;

  const dashboard = dashboardQuery.data;
  const setup = setupQuery.data;
  const pendingActivation = Boolean(
    access.summary?.pending_activation_clinic_ids.includes(activeClinicId),
  );

  return (
    <div className="space-y-7">
      <PageHeader
        title={activeClinic.name}
        description="Estado operativo y próximos pasos de tu clínica."
      />

      {isClientPortal && pendingActivation ? (
        <Card className="border-[#f1d397] bg-[#fff9ed]">
          <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#fff0cf] text-[#9a6818]">
              <Clock3 className="size-5" />
            </span>
            <div className="flex-1">
              <p className="font-semibold text-[#765116]">Número pendiente de activación</p>
              <p className="mt-1 text-sm text-[#80672f]">
                El pago está confirmado. Autogal asignará y activará el número en un plazo máximo de 24 horas.
              </p>
            </div>
            <Button asChild variant="outline">
              <Link to={`/clinics/${activeClinicId}/purchases`}>Ver estado</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {isClientPortal ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-[#dfe5f5]">
            <CardContent className="flex items-center gap-4 p-5">
              <span className="grid size-11 place-items-center rounded-xl bg-[#eef2ff] text-[#315efb]">
                <Settings className="size-5" />
              </span>
              <div className="flex-1">
                <p className="font-semibold text-[#27334a]">Configuración de la clínica</p>
                <p className="mt-1 text-sm text-[#748095]">Datos, trabajadores, recursos, servicios, calendario y conocimiento.</p>
              </div>
              <Button asChild size="sm" variant="outline">
                <Link to={`/clinics/${activeClinicId}/settings/general`}>
                  Configurar <ArrowRight className="size-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
          <Card className="border-[#dfe5f5]">
            <CardContent className="flex items-center gap-4 p-5">
              <span className="grid size-11 place-items-center rounded-xl bg-[#eef2ff] text-[#315efb]">
                <Bot className="size-5" />
              </span>
              <div className="flex-1">
                <p className="font-semibold text-[#27334a]">Configuración del asistente</p>
                <p className="mt-1 text-sm text-[#748095]">Voz, comportamiento, reservas y personalización.</p>
              </div>
              <Button asChild size="sm" variant="outline">
                <Link to={`/clinics/${activeClinicId}/assistant`}>
                  Configurar <ArrowRight className="size-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={dashboard.configuration_complete ? CheckCircle2 : CircleX} label="Configuración completa" value={dashboard.configuration_complete ? "Sí" : "No"} hint={dashboard.configuration_complete ? "Lista para producción" : `${setup.blocking_errors.length} bloqueo(s)`} accent={dashboard.configuration_complete ? "green" : "amber"} />
        <MetricCard icon={CalendarCheck2} label="Google Calendar" value={dashboard.google_calendar_connected ? "Sí" : "No"} hint={dashboard.google_calendar_connected ? "OAuth conectado" : "Conexión pendiente"} accent={dashboard.google_calendar_connected ? "green" : "amber"} />
        <MetricCard icon={Phone} label="Número configurado" value={dashboard.phone_number_configured ? "Sí" : "No"} hint="Número activo" accent={dashboard.phone_number_configured ? "green" : "amber"} />
        <MetricCard icon={Bot} label="Asistente activo" value={dashboard.assistant_active ? "Sí" : "No"} hint="Configuración efectiva" accent={dashboard.assistant_active ? "green" : "amber"} />
        <MetricCard icon={Users} label="Trabajadores activos" value={dashboard.active_workers} accent="violet" />
        <MetricCard icon={Stethoscope} label="Servicios reservables" value={dashboard.bookable_services} accent="green" />
        <MetricCard icon={PhoneCall} label="Llamadas últimas 24h" value={dashboard.calls_last_24h} />
        <MetricCard icon={CalendarClock} label="Citas próximas" value={dashboard.upcoming_appointments} hint="Siguientes 30 días" accent="violet" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader><CardTitle>Salud reciente</CardTitle><CardDescription>Errores de llamadas y eventos técnicos en 24 horas.</CardDescription></CardHeader>
          <CardContent><div className={`flex items-center gap-4 rounded-xl p-5 ${dashboard.recent_errors ? "bg-[#fff3f4] text-[#9e3945]" : "bg-[#eef9f2] text-[#28764a]"}`}><AlertTriangle className="size-7" /><div><p className="text-3xl font-bold">{dashboard.recent_errors}</p><p className="mt-1 text-sm font-medium">Errores recientes</p></div></div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4"><div><CardTitle>Última llamada recibida</CardTitle><CardDescription>Excluye simulaciones y pruebas del navegador.</CardDescription></div><Button asChild variant="ghost" size="sm"><Link to={`/clinics/${activeClinicId}/conversations`}>Ver llamadas</Link></Button></CardHeader>
          <CardContent>{dashboard.last_call ? <div className="rounded-xl border border-[#e5e9ef] p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold text-[#27334a]">{dashboard.last_call.caller_phone}</p><p className="mt-1 text-sm text-[#748095]">A {dashboard.last_call.called_number} · {formatDateTime(dashboard.last_call.started_at)}</p></div><div className="flex flex-wrap gap-2"><StatusBadge status={callStatusTone(dashboard.last_call.status)}>{callStatusLabels[dashboard.last_call.status]}</StatusBadge>{dashboard.last_call.outcome ? <StatusBadge status={callOutcomeTone(dashboard.last_call.outcome)}>{callOutcomeLabels[dashboard.last_call.outcome]}</StatusBadge> : null}</div></div></div> : <p className="py-8 text-center text-sm text-[#7b8799]">Todavía no hay llamadas reales.</p>}</CardContent>
        </Card>
      </div>

      <SetupChecklist status={setup} />
      {setup.warnings.length ? <Card className="border-[#eed9b4] bg-[#fffbf2]"><CardContent className="pt-5"><p className="font-semibold text-[#8c641d]">Avisos no bloqueantes</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[#80672f]">{setup.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></CardContent></Card> : null}
    </div>
  );
}
