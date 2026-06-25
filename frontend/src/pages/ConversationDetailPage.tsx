import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Clipboard,
  Download,
  Eraser,
  PhoneOff,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import {
  anonymizeCallPhone,
  deleteCall,
  deleteCallContent,
  getCall,
  getCallDebug,
} from "@/api/calls";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useClinicRoute } from "@/hooks/useClinicRoute";
import {
  callOutcomeLabels,
  callOutcomeTone,
  callStatusLabels,
  callStatusTone,
  formatDuration,
} from "@/lib/calls";
import { formatDateTime } from "@/lib/format";
import type { CallEvent } from "@/schemas/domain";

type PrivacyAction = "content" | "phone" | "conversation" | null;

function EventList({
  events,
  empty,
}: {
  events: CallEvent[];
  empty: string;
}) {
  if (!events.length) {
    return <p className="text-sm text-[#7a8699]">{empty}</p>;
  }
  return (
    <div className="space-y-3">
      {events.map((event) => (
        <div
          key={event.id}
          className="rounded-xl border border-[#e6eaf0] bg-[#fafbfc] p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-mono text-xs font-semibold text-[#31405b]">
              {event.event_type}
            </p>
            <span className="text-xs text-[#7b8799]">
              {formatDateTime(event.created_at)}
            </span>
          </div>
          <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-[#111827] p-3 text-xs text-[#dbe4f3]">
            {JSON.stringify(event.payload_json, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  );
}

export function ConversationDetailPage() {
  const clinicId = useClinicRoute();
  const { callId } = useParams<{ callId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [privacyAction, setPrivacyAction] = useState<PrivacyAction>(null);
  const query = useQuery({
    queryKey: ["call", clinicId, callId],
    queryFn: () => getCall(clinicId as string, callId as string),
    enabled: Boolean(clinicId && callId),
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["call", clinicId, callId] }),
      queryClient.invalidateQueries({ queryKey: ["calls", clinicId] }),
    ]);
  };
  const privacyMutation = useMutation({
    mutationFn: async (action: Exclude<PrivacyAction, null>) => {
      if (action === "content") {
        return deleteCallContent(clinicId as string, callId as string);
      }
      if (action === "phone") {
        return anonymizeCallPhone(clinicId as string, callId as string);
      }
      return deleteCall(clinicId as string, callId as string);
    },
    onSuccess: async (result) => {
      setPrivacyAction(null);
      if (result.status === "deleted") {
        toast.success("Conversación eliminada");
        navigate(`/clinics/${clinicId}/conversations`);
        return;
      }
      await refresh();
      toast.success(
        result.status === "content_deleted"
          ? "Transcripción y resumen borrados"
          : "Datos personales anonimizados",
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const downloadDebug = async () => {
    try {
      const debug = await getCallDebug(clinicId as string, callId as string);
      const blob = new Blob([JSON.stringify(debug, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `call-${callId}-debug.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Descarga fallida");
    }
  };

  if (query.isLoading) return <LoadingState rows={8} />;
  if (query.error) return <ErrorState error={query.error} />;
  if (!query.data) return null;
  const call = query.data;

  return (
    <div className="space-y-7">
      <PageHeader
        title="Detalle de conversación"
        description={`${call.clinic_name} · ${formatDateTime(call.started_at)}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to={`/clinics/${clinicId}/conversations`}>
                <ArrowLeft className="size-4" />
                Volver
              </Link>
            </Button>
            <Button variant="outline" onClick={() => void downloadDebug()}>
              <Download className="size-4" />
              Descargar JSON
            </Button>
          </div>
        }
      />

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <p className="text-xs font-semibold uppercase text-[#7b8799]">Estado</p>
          <div className="mt-3">
            <StatusBadge status={callStatusTone(call.status)}>
              {callStatusLabels[call.status]}
            </StatusBadge>
          </div>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-semibold uppercase text-[#7b8799]">
            Resultado
          </p>
          <div className="mt-3">
            {call.outcome ? (
              <StatusBadge status={callOutcomeTone(call.outcome)}>
                {callOutcomeLabels[call.outcome]}
              </StatusBadge>
            ) : (
              "—"
            )}
          </div>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-semibold uppercase text-[#7b8799]">
            Duración
          </p>
          <p className="mt-2 text-2xl font-bold text-[#27334a]">
            {formatDuration(call.duration_seconds)}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-semibold uppercase text-[#7b8799]">Cita</p>
          <div className="mt-3">
            <StatusBadge status={call.appointment ? "success" : "neutral"}>
              {call.appointment ? "Cita creada" : "Sin cita"}
            </StatusBadge>
          </div>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Datos de llamada</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {[
              ["Clínica", call.clinic_name],
              ["Número llamante", call.caller_phone],
              ["Número llamado", call.called_number],
              ["Nombre", call.caller_name || "No identificado"],
              ["Inicio", formatDateTime(call.started_at)],
              ["Fin", formatDateTime(call.ended_at)],
              ["Intención", call.detected_intent || "—"],
              ["OpenAI call ID", call.openai_call_id],
            ].map(([label, value]) => (
              <div key={label}>
                <p className="text-xs font-semibold uppercase text-[#7b8799]">
                  {label}
                </p>
                <p className="mt-1 break-all text-sm text-[#27334a]">{value}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cita asociada</CardTitle>
          </CardHeader>
          <CardContent>
            {call.appointment ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs uppercase text-[#7b8799]">Paciente</p>
                  <p className="mt-1 font-semibold">{call.appointment.patient_name}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-[#7b8799]">Fecha</p>
                  <p className="mt-1">{formatDateTime(call.appointment.start_at)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-[#7b8799]">Trabajador</p>
                  <p className="mt-1">{call.appointment.worker_name}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-[#7b8799]">Servicio</p>
                  <p className="mt-1">{call.appointment.service_name || "—"}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-[#7a8699]">
                Esta conversación no creó ninguna cita.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle>Resumen</CardTitle>
          <Button
            size="sm"
            variant="outline"
            disabled={!call.summary_text}
            onClick={() => {
              void navigator.clipboard.writeText(call.summary_text ?? "");
              toast.success("Resumen copiado");
            }}
          >
            <Clipboard className="size-4" />
            Copiar
          </Button>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm leading-6 text-[#39465d]">
            {call.summary_text || "No hay resumen guardado."}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transcripción</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-[480px] overflow-y-auto whitespace-pre-wrap rounded-xl bg-[#f7f8fa] p-4 text-sm leading-6 text-[#344158]">
            {call.transcript_text || "No hay transcripción guardada."}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Tool calls ({call.tool_calls.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <EventList events={call.tool_calls} empty="No se registraron tools." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Errores ({call.errors.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <EventList events={call.errors} empty="No hay errores registrados." />
          </CardContent>
        </Card>
      </div>

      <Card>
        <details>
          <summary className="cursor-pointer list-none p-5 font-semibold text-[#27334a]">
            Eventos técnicos ({call.events.length})
          </summary>
          <div className="border-t border-[#e6eaf0] p-5">
            <EventList events={call.events} empty="No hay eventos guardados." />
          </div>
        </details>
      </Card>

      <Card className="border-[#f0d7da]">
        <CardHeader>
          <CardTitle>Privacidad y borrado</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => setPrivacyAction("content")}>
            <Eraser className="size-4" />
            Borrar transcript y resumen
          </Button>
          <Button variant="outline" onClick={() => setPrivacyAction("phone")}>
            <ShieldCheck className="size-4" />
            Anonimizar teléfono
          </Button>
          <Button
            variant="destructive"
            onClick={() => setPrivacyAction("conversation")}
          >
            {call.appointment ? (
              <PhoneOff className="size-4" />
            ) : (
              <Trash2 className="size-4" />
            )}
            Borrar conversación
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={privacyAction !== null}
        onOpenChange={(open) => {
          if (!open) setPrivacyAction(null);
        }}
        title={
          privacyAction === "content"
            ? "Borrar contenido"
            : privacyAction === "phone"
              ? "Anonimizar teléfono"
              : "Borrar conversación"
        }
        description={
          privacyAction === "content"
            ? "Se borrarán transcripción y resumen. La cita se conserva."
            : privacyAction === "phone"
              ? "Se eliminará la identidad de la llamada. La cita se conserva."
              : call.appointment
                ? "Como existe una cita, la llamada será anonimizada y la cita seguirá intacta."
                : "La conversación y sus eventos se eliminarán por completo."
        }
        confirmLabel="Continuar"
        isPending={privacyMutation.isPending}
        onConfirm={() => {
          if (privacyAction) privacyMutation.mutate(privacyAction);
        }}
      />
    </div>
  );
}
