import type { CallOutcome, CallStatus } from "@/schemas/domain";

export const callStatusLabels: Record<CallStatus, string> = {
  incoming: "Entrante",
  active: "Activa",
  completed: "Completada",
  failed: "Fallida",
  transferred: "Transferida",
};

export const callOutcomeLabels: Record<CallOutcome, string> = {
  appointment_created: "Cita creada",
  cancelled: "Cancelada",
  transferred: "Transferida",
  no_action: "Sin acción",
  failed: "Fallida",
};

export function callStatusTone(
  value: CallStatus,
): "success" | "warning" | "danger" | "neutral" | "info" {
  if (value === "completed") return "success";
  if (value === "failed") return "danger";
  if (value === "active") return "info";
  if (value === "transferred") return "warning";
  return "neutral";
}

export function callOutcomeTone(
  value: CallOutcome,
): "success" | "warning" | "danger" | "neutral" | "info" {
  if (value === "appointment_created") return "success";
  if (value === "failed") return "danger";
  if (value === "transferred") return "warning";
  return "neutral";
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}
