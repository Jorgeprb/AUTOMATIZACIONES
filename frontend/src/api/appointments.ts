import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  AppointmentAnalysis,
  AppointmentStatus,
} from "@/schemas/domain";

export interface AppointmentFilters {
  page?: number;
  pageSize?: number;
  dateFrom?: string;
  dateTo?: string;
  status?: AppointmentStatus | "";
  workerId?: string;
  serviceId?: string;
  patientPhone?: string;
  source?: "voice_bot" | "admin_panel" | "";
}

export function listAppointments(
  clinicId: string,
  filters: AppointmentFilters = {},
): Promise<Page<AppointmentAnalysis>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/appointments${toQuery({
      page: filters.page ?? 1,
      page_size: filters.pageSize ?? 20,
      date_from: filters.dateFrom,
      date_to: filters.dateTo,
      status: filters.status,
      worker_id: filters.workerId,
      service_id: filters.serviceId,
      patient_phone: filters.patientPhone,
      source: filters.source,
    })}`,
  );
}

export function cancelAppointment(
  clinicId: string,
  appointmentId: string,
): Promise<AppointmentAnalysis> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/appointments/${appointmentId}/cancel`,
    { method: "POST" },
  );
}
