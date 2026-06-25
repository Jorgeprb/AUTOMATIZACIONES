import {
  Bot,
  Building2,
  CalendarDays,
  FlaskConical,
  LayoutDashboard,
  MessageSquareText,
  Settings,
  Sparkles,
  Stethoscope,
  Users,
  Workflow,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { useActiveClinic } from "@/hooks/useActiveClinic";

const baseItems = [
  { label: "Dashboard", icon: LayoutDashboard, path: "/" },
  { label: "Clínicas", icon: Building2, path: "/clinics" },
];

const clinicItems = [
  { label: "Trabajadores", icon: Users, suffix: "workers" },
  { label: "Servicios", icon: Stethoscope, suffix: "services" },
  { label: "Asistente", icon: Bot, suffix: "assistant" },
  { label: "Flujos", icon: Workflow, suffix: "flows" },
  { label: "Conocimiento", icon: Sparkles, suffix: "knowledge" },
  { label: "Conversaciones", icon: MessageSquareText, suffix: "conversations" },
  { label: "Calendario", icon: CalendarDays, suffix: "calendar" },
  { label: "Consola de prueba", icon: FlaskConical, suffix: "test" },
];

function NavItem({
  to,
  label,
  icon: Icon,
  disabled = false,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  disabled?: boolean;
  onNavigate?: () => void;
}) {
  if (disabled) {
    return (
      <span className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[#8d97a7] opacity-60">
        <Icon className="size-[18px]" />
        {label}
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
      {label}
    </NavLink>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { activeClinicId } = useActiveClinic();
  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex h-18 items-center border-b border-[#edf0f4] px-5">
        <div className="grid size-9 place-items-center rounded-xl bg-[#315efb] text-white shadow-lg shadow-[#315efb]/20">
          <Bot className="size-5" />
        </div>
        <div className="ml-3">
          <p className="text-sm font-bold tracking-tight text-[#172033]">
            Clinic Voice
          </p>
          <p className="text-[11px] font-medium text-[#8791a2]">Admin Platform</p>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        <div className="space-y-1">
          {baseItems.map((item) => (
            <NavItem
              key={item.path}
              label={item.label}
              icon={item.icon}
              to={item.path}
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
                disabled={!activeClinicId}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </div>
      </nav>

      <div className="border-t border-[#edf0f4] p-3">
        <NavItem
          to="/settings"
          label="Configuración"
          icon={Settings}
          onNavigate={onNavigate}
        />
      </div>
    </div>
  );
}
