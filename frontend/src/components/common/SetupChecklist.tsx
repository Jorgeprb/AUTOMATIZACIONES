import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
} from "lucide-react";
import { Link } from "react-router-dom";

import { StatusBadge } from "@/components/common/StatusBadge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { SetupStatus } from "@/schemas/domain";

export function SetupChecklist({ status }: { status: SetupStatus }) {
  const completedCount = status.items.filter((item) => item.completed).length;
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Checklist de puesta en producción</CardTitle>
          <CardDescription>
            {completedCount} de {status.items.length} pasos completados.
          </CardDescription>
        </div>
        <StatusBadge status={status.completed ? "success" : "warning"}>
          {status.completed ? "Lista" : "Pendiente"}
        </StatusBadge>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.blocking_errors.length ? (
          <div className="flex gap-3 rounded-xl border border-[#f1c8cc] bg-[#fff5f6] p-4 text-sm text-[#963945]">
            <AlertTriangle className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-semibold">Bloqueos para producción</p>
              <p className="mt-1">
                {status.blocking_errors.join(" · ")}
              </p>
            </div>
          </div>
        ) : null}

        <div className="grid gap-3 lg:grid-cols-2">
          {status.items.map((item) => (
            <Link
              key={item.key}
              to={item.href}
              className="group flex items-start gap-3 rounded-xl border border-[#e4e8ef] p-4 transition hover:border-[#bfcdf8] hover:bg-[#f8faff]"
            >
              {item.completed ? (
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[#26814d]" />
              ) : (
                <CircleDashed className="mt-0.5 size-5 shrink-0 text-[#a87822]" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-[#27334a]">{item.label}</p>
                  {item.automatic ? (
                    <span className="rounded-full bg-[#eef2f7] px-2 py-0.5 text-[10px] font-semibold uppercase text-[#718096]">
                      Automático
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-sm leading-5 text-[#748095]">
                  {item.help}
                </p>
              </div>
              <ArrowRight className="mt-1 size-4 shrink-0 text-[#9aa4b5] transition group-hover:translate-x-0.5 group-hover:text-[#315efb]" />
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
