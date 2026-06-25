import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, Eye, Stethoscope, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { previewPrompt } from "@/api/assistants";
import { getPromptContextPreview } from "@/api/knowledge";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { knowledgeCategoryLabels } from "@/schemas/knowledge";

export function PromptContextPreview({ clinicId }: { clinicId: string }) {
  const [promptOpen, setPromptOpen] = useState(false);
  const contextQuery = useQuery({
    queryKey: ["prompt-context-preview", clinicId],
    queryFn: () => getPromptContextPreview(clinicId),
  });
  const promptMutation = useMutation({
    mutationFn: (configId: string) => previewPrompt(clinicId, configId),
    onSuccess: () => setPromptOpen(true),
    onError: (error: Error) => toast.error(error.message),
  });

  if (contextQuery.isLoading) return <LoadingState rows={4} />;
  if (contextQuery.error) return <ErrorState error={contextQuery.error} />;
  const context = contextQuery.data;
  if (!context) return null;

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Contexto efectivo del LLM</CardTitle>
            <p className="mt-1 text-sm text-[#758197]">
              Solo aparecen datos activos que pueden entrar en el prompt.
            </p>
          </div>
          <Button
            variant="outline"
            disabled={!context.assistant_config_id || promptMutation.isPending}
            onClick={() => {
              if (context.assistant_config_id) {
                promptMutation.mutate(context.assistant_config_id);
              }
            }}
          >
            <Eye className="size-4" />
            Ver prompt final
          </Button>
        </CardHeader>
        <CardContent className="space-y-5">
          {context.warnings.length ? (
            <div className="space-y-2">
              {context.warnings.map((warning) => (
                <div
                  key={warning}
                  className="flex items-start gap-2 rounded-lg border border-[#ffe0a5] bg-[#fff9ec] px-3 py-2 text-sm text-[#78591d]"
                >
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  {warning}
                </div>
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-xl border p-4">
              <div className="flex items-center gap-2">
                <Stethoscope className="size-4 text-[#315efb]" />
                <p className="font-semibold">Servicios activos</p>
              </div>
              <div className="mt-3 space-y-3">
                {context.services.map((service) => (
                  <div key={service.id}>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium">{service.public_name}</p>
                      <StatusBadge
                        status={service.is_bookable_by_bot ? "success" : "neutral"}
                      >
                        {service.is_bookable_by_bot ? "Reservable" : "Solo información"}
                      </StatusBadge>
                    </div>
                    <p className="mt-1 text-xs text-[#758197]">{service.price}</p>
                  </div>
                ))}
                {!context.services.length ? (
                  <p className="text-sm text-[#8893a4]">Sin servicios activos.</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl border p-4">
              <div className="flex items-center gap-2">
                <Users className="size-4 text-[#315efb]" />
                <p className="font-semibold">Trabajadores</p>
              </div>
              <div className="mt-3 space-y-2">
                {context.workers.map((worker) => (
                  <div key={worker.id} className="text-sm">
                    <p className="font-medium">{worker.name}</p>
                    <p className="text-xs text-[#758197]">
                      {worker.role} ·{" "}
                      {worker.calendar_linked ? "con calendario" : "sin calendario"}
                    </p>
                  </div>
                ))}
                {!context.workers.length ? (
                  <p className="text-sm text-[#8893a4]">Sin trabajadores activos.</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-xl border p-4">
              <div className="flex items-center gap-2">
                <Bot className="size-4 text-[#315efb]" />
                <p className="font-semibold">Conocimiento activo</p>
              </div>
              <div className="mt-3 space-y-2">
                {context.knowledge_items.map((item) => (
                  <div key={item.id}>
                    <p className="text-sm font-medium">{item.title}</p>
                    <p className="text-xs text-[#758197]">
                      {knowledgeCategoryLabels[item.category]} · prioridad {item.priority}
                    </p>
                  </div>
                ))}
                {!context.knowledge_items.length ? (
                  <p className="text-sm text-[#8893a4]">Sin contexto activo.</p>
                ) : null}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog open={promptOpen} onOpenChange={setPromptOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Prompt final renderizado</DialogTitle>
            <DialogDescription>
              Configuración activa más servicios, trabajadores y conocimiento.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-xl bg-[#111827] p-5 text-xs leading-6 text-[#e5e7eb]">
            {promptMutation.data?.prompt}
          </pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
