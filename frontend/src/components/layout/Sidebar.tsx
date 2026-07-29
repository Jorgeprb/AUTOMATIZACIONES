import {
  BarChart3,
  Bot,
  Box,
  Building2,
  CalendarDays,
  CreditCard,
  FlaskConical,
  LayoutDashboard,
  LockKeyhole,
  MessageSquareText,
  Settings,
  Sparkles,
  Stethoscope,
  UserRoundCog,
  Users,
  Workflow,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getGlobalAnalytics } from "@/api/enterprise";
import { useCommercialAccess } from "@/hooks/useCommercialAccess";
import { useActiveClinic } from "@/hooks/useActiveClinic";
import { getCurrentAdmin } from "@/lib/auth";
import { isAdminPortal, isClientPortal } from "@/lib/portal";
import { cn } from "@/lib/utils";

const adminClinicItems = [
  { label: "Clientes", icon: UserRoundCog, suffix: "customers" },
  { label: "Trabajadores", icon: Users, suffix: "workers" },
  { label: "Recursos", icon: Box, suffix: "resources" },
  { label: "Estadísticas", icon: BarChart3, suffix: "statistics" },
  { label: "Servicios", icon: Stethoscope, suffix: "services" },
  { label: "Asistente", icon: Bot, suffix: "assistant" },
  { label: "Flujos", icon: Workflow, suffix: "flows" },
  { label: "Conocimiento", icon: Sparkles, suffix: "knowledge" },
  { label: "Conversaciones", icon: MessageSquareText, suffix: "conversations" },
  { label: "Calendario", icon: CalendarDays, suffix: "calendar" },
  { label: "Consola de prueba", icon: FlaskConical, suffix: "test" },
  { label: "Compras y suscripciones", icon: CreditCard, suffix: "purchases" },
];

const clientClinicItems = [
  { label: "Ajustes de la clínica", icon: Settings, suffix: "settings/general" },
  { label: "Configuración del asistente", icon: Bot, suffix: "assistant" },
  { label: "Clientes", icon: UserRoundCog, suffix: "customers" },
  { label: "Estadísticas", icon: BarChart3, suffix: "statistics" },
  { label: "Conversaciones", icon: MessageSquareText, suffix: "conversations" },
  { label: "Calendario", icon: CalendarDays, suffix: "calendar" },
  { label: "Consola de prueba", icon: FlaskConical, suffix: "test" },
];

function NavItem({
  to,
  label,
  icon: Icon,
  disabled = false,
  badge,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  disabled?: boolean;
  badge?: number;
  onNavigate?: () => void;
}) {
  if (disabled) {
    return (
      <span
        className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[#9aa3b1]"
        title="Compra un número Autogal para desbloquear esta función"
      >
        <Icon className="size-[18px] opacity-70" />
        <span className="flex-1">{label}</span>
        <LockKeyhole className="size-3.5 opacity-70" />
      </span>
    );
  }
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-[#eaf0ff] text-[#2e55dd]"
            : "text-[#5e6b80] hover:bg-[#f0f3f7] hover:text-[#1e2a40]",
        )
      }
    >
      <Icon className="size-[18px]" />
      <span className="flex-1">{label}</span>
      {badge ? (
        <span className="min-w-5 rounded-full bg-[#d83b4d] px-1.5 py-0.5 text-center text-[10px] font-bold text-white">
          {badge > 99 ? "99+" : badge}
        </span>
      ) : null}
    </NavLink>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { activeClinicId } = useActiveClinic();
  const auth = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getCurrentAdmin,
    staleTime: 60_000,
  });
  const access = useCommercialAccess();
  const superAdmin = auth.data?.role === "super_admin";
  const global = useQuery({
    queryKey: ["admin", "global-analytics", "sidebar"],
    queryFn: getGlobalAnalytics,
    enabled: isAdminPortal && superAdmin,
    refetchInterval: 60_000,
  });
  const pendingProvisioning = Number(global.data?.pending_provisioning ?? 0);
  const locked = isClientPortal && !access.unlocked;
  const clinicItems = isClientPortal ? clientClinicItems : adminClinicItems;
  const purchasesPath = activeClinicId
    ? `/clinics/${activeClinicId}/purchases`
    : "/clinics";
  const baseItems = [
    { label: "Dashboard", icon: LayoutDashboard, path: "/" },
    {
      label: isClientPortal ? "Mis clínicas" : "Clínicas",
      icon: Building2,
      path: "/clinics",
    },
    ...(isClientPortal
      ? [{ label: "Compras y suscripciones", icon: CreditCard, path: purchasesPath }]
      : []),
    ...(isAdminPortal && superAdmin
      ? [
          { label: "Usuarios y accesos", icon: UserRoundCog, path: "/users" },
          {
            label: "Negocio y provisión",
            icon: CreditCard,
            path: "/business",
            badge: pendingProvisioning,
          },
        ]
      : []),
  ];

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex h-18 items-center border-b border-[#edf0f4] px-5">
        <div className="grid size-9 place-items-center rounded-xl bg-[#315efb] text-white shadow-lg shadow-[#315efb]/20">
          <Bot className="size-5" />
        </div>
        <div className="ml-3">
          <p className="text-sm font-bold tracking-tight text-[#172033]">Autogal</p>
          <p className="text-[11px] font-medium text-[#8791a2]">
            {isClientPortal ? "Portal de cliente" : "Administración global"}
          </p>
        </div>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        <div className="space-y-1">
          {baseItems.map((item) => (
            <NavItem
              key={item.path}
              to={item.path}
              label={item.label}
              icon={item.icon}
              badge={"badge" in item ? item.badge : undefined}
              onNavigate={onNavigate}
            />
          ))}
        </div>
        <div>
          <p className="mb-2 px-3 text-[11px] font-bold uppercase tracking-[0.14em] text-[#9aa3b2]">
            Clínica activa
          </p>
          <div className="space-y-1">
            {clinicItems.map((item) => (
              <NavItem
                key={item.suffix}
                label={item.label}
                icon={item.icon}
                to={
                  activeClinicId
                    ? `/clinics/${activeClinicId}/${item.suffix}`
                    : "/clinics"
                }
                disabled={!activeClinicId || locked}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </div>
      </nav>
      {!isClientPortal ? (
        <div className="border-t border-[#edf0f4] p-3">
          <NavItem
            to="/settings"
            label="Mi cuenta"
            icon={Settings}
            onNavigate={onNavigate}
          />
        </div>
      ) : null}
    </div>
  );
}
