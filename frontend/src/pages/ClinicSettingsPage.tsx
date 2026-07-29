import { CalendarDays, Stethoscope, Sparkles, Users, Box } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";

import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { CalendarPage } from "@/pages/CalendarPage";
import { ClinicDetailPage } from "@/pages/ClinicDetailPage";
import { KnowledgePage } from "@/pages/KnowledgePage";
import { ResourcesPage } from "@/pages/ResourcesPage";
import { ServicesPage } from "@/pages/ServicesPage";
import { WorkersPage } from "@/pages/WorkersPage";

const tabs = [
  { id: "general", label: "Datos generales", icon: Stethoscope },
  { id: "workers", label: "Trabajadores", icon: Users },
  { id: "resources", label: "Recursos", icon: Box },
  { id: "services", label: "Servicios", icon: Stethoscope },
  { id: "calendar", label: "Integración de calendario", icon: CalendarDays },
  { id: "knowledge", label: "Conocimiento", icon: Sparkles },
] as const;


export function ClinicSettingsPage() {
  const { clinicId, section = "general" } = useParams<{
    clinicId: string;
    section?: string;
  }>();
  if (!clinicId) return <Navigate to="/clinics" replace />;
  if (!tabs.some((tab) => tab.id === section)) {
    return <Navigate to={`/clinics/${clinicId}/settings/general`} replace />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ajustes de la clínica"
        description="Configura desde un único lugar los datos generales, equipo, servicios, recursos, calendario y conocimiento."
      />
      <Card>
        <CardContent className="flex gap-2 overflow-x-auto p-3">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <Link
                key={tab.id}
                to={`/clinics/${clinicId}/settings/${tab.id}`}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors",
                  section === tab.id
                    ? "bg-[#eaf0ff] text-[#2e55dd]"
                    : "text-[#657187] hover:bg-[#f3f5f8] hover:text-[#28354c]",
                )}
              >
                <Icon className="size-4" />
                {tab.label}
              </Link>
            );
          })}
        </CardContent>
      </Card>
      {section === "general" ? <ClinicDetailPage embedded /> : null}
      {section === "workers" ? <WorkersPage /> : null}
      {section === "resources" ? <ResourcesPage /> : null}
      {section === "services" ? <ServicesPage /> : null}
      {section === "calendar" ? <CalendarPage /> : null}
      {section === "knowledge" ? <KnowledgePage /> : null}
    </div>
  );
}
