import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Server, ShieldCheck, Timer } from "lucide-react";

import { apiConfig, getHealth } from "@/api/client";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentAdmin } from "@/lib/auth";

export function SettingsPage() {
  const healthQuery = useQuery({ queryKey: ["health", "settings"], queryFn: getHealth });
  const authQuery = useQuery({ queryKey: ["auth", "me"], queryFn: getCurrentAdmin, retry: false });
  return (
    <div className="space-y-7">
      <PageHeader title="Mi cuenta" description="Identidad, permisos y estado de la sesión." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Server className="size-5 text-[#315efb]" />Backend</CardTitle><CardDescription>FastAPI configurado para este frontend.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-xl bg-[#f7f9fc] p-4"><p className="text-xs font-semibold uppercase text-[#8590a2]">URL base</p><p className="mt-2 break-all font-mono text-sm text-[#364259]">{apiConfig.baseUrl}</p></div>
            <div className="flex items-center justify-between"><span className="text-sm text-[#657186]">Estado</span><StatusBadge status={healthQuery.data ? "success" : "danger"}>{healthQuery.data ? "Conectado" : "Sin conexión"}</StatusBadge></div>
            {healthQuery.data ? <div className="flex items-center gap-2 text-sm text-[#526078]"><CheckCircle2 className="size-4 text-[#24804a]" />{healthQuery.data.service} · {healthQuery.data.environment}</div> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-5 text-[#7650c8]" />Sesión administrativa</CardTitle><CardDescription>La credencial no se incluye en el JavaScript ni se guarda en localStorage.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-xl bg-[#f7f9fc] p-4"><div className="flex items-center gap-3"><ShieldCheck className="size-5 text-[#315efb]" /><span className="text-sm font-semibold text-[#364259]">{authQuery.data?.display_name || authQuery.data?.email || authQuery.data?.username || "Usuario"}</span></div><StatusBadge status={authQuery.data ? "success" : "danger"}>{authQuery.data?.role ?? "No autenticado"}</StatusBadge></div>
            <div className="flex items-center gap-2 text-sm text-[#758197]"><Timer className="size-4" />Peticiones con timeout de {Math.round(apiConfig.timeoutMs / 1000)} segundos y protección CSRF.</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
