import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Server, ShieldCheck } from "lucide-react";

import { apiConfig, getHealth } from "@/api/client";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function SettingsPage() {
  const healthQuery = useQuery({
    queryKey: ["health", "settings"],
    queryFn: getHealth,
  });
  return (
    <div className="space-y-7">
      <PageHeader
        title="Configuración"
        description="Conectividad local del panel. Las claves se leen desde variables de Vite."
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="size-5 text-[#315efb]" />
              Backend
            </CardTitle>
            <CardDescription>FastAPI configurado para este frontend.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-xl bg-[#f7f9fc] p-4">
              <p className="text-xs font-semibold uppercase text-[#8590a2]">
                URL base
              </p>
              <p className="mt-2 break-all font-mono text-sm text-[#364259]">
                {apiConfig.baseUrl}
              </p>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#657186]">Estado</span>
              <StatusBadge status={healthQuery.data ? "success" : "danger"}>
                {healthQuery.data ? "Conectado" : "Sin conexión"}
              </StatusBadge>
            </div>
            {healthQuery.data ? (
              <div className="flex items-center gap-2 text-sm text-[#526078]">
                <CheckCircle2 className="size-4 text-[#24804a]" />
                {healthQuery.data.service} · {healthQuery.data.environment}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-5 text-[#7650c8]" />
              Autenticación administrativa
            </CardTitle>
            <CardDescription>
              Estado de la variable VITE_ADMIN_API_KEY.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-xl bg-[#f7f9fc] p-4">
              <div className="flex items-center gap-3">
                <ShieldCheck className="size-5 text-[#315efb]" />
                <span className="text-sm font-semibold text-[#364259]">
                  API key del panel
                </span>
              </div>
              <StatusBadge status={apiConfig.hasAdminKey ? "success" : "danger"}>
                {apiConfig.hasAdminKey ? "Configurada" : "Falta"}
              </StatusBadge>
            </div>
            <p className="text-sm leading-6 text-[#758197]">
              La clave nunca se muestra en pantalla. Este mecanismo es adecuado
              para el MVP local, pero no sustituye login y permisos de usuario.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
