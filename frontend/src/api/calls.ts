import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  CallAnalysis,
  CallAnalysisDetail,
  CallDebugResponse,
  CallEvent,
  CallOutcome,
  CallPrivacyResponse,
  CallStatus,
} from "@/schemas/domain";

export interface CallFilters {
  page?: number;
  pageSize?: number;
  dateFrom?: string;
  dateTo?: string;
  status?: CallStatus | "";
  outcome?: CallOutcome | "";
  phone?: string;
  workerId?: string;
  serviceId?: string;
}

export function listCalls(
  clinicId: string,
  filters: CallFilters = {},
): Promise<Page<CallAnalysis>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/calls${toQuery({
      page: filters.page ?? 1,
      page_size: filters.pageSize ?? 20,
      date_from: filters.dateFrom,
      date_to: filters.dateTo,
      status: filters.status,
      outcome: filters.outcome,
      phone: filters.phone,
      worker_id: filters.workerId,
      service_id: filters.serviceId,
    })}`,
  );
}

export function getCall(
  clinicId: string,
  callId: string,
): Promise<CallAnalysisDetail> {
  return apiRequest(`/api/admin/clinics/${clinicId}/calls/${callId}`);
}

export function listCallEvents(
  clinicId: string,
  callId: string,
): Promise<Page<CallEvent>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/calls/${callId}/events?page_size=200`,
  );
}

export function listCallToolCalls(
  clinicId: string,
  callId: string,
): Promise<CallEvent[]> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/calls/${callId}/tool-calls`,
  );
}

export function deleteCallContent(
  clinicId: string,
  callId: string,
): Promise<CallPrivacyResponse> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/calls/${callId}/content`,
    { method: "DELETE" },
  );
}

export function anonymizeCallPhone(
  clinicId: string,
  callId: string,
): Promise<CallPrivacyResponse> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/calls/${callId}/anonymize-phone`,
    { method: "POST" },
  );
}

export function deleteCall(
  clinicId: string,
  callId: string,
): Promise<CallPrivacyResponse> {
  return apiRequest(`/api/admin/clinics/${clinicId}/calls/${callId}`, {
    method: "DELETE",
  });
}

export function getCallDebug(
  clinicId: string,
  callId: string,
): Promise<CallDebugResponse> {
  return apiRequest(`/api/admin/clinics/${clinicId}/calls/${callId}/debug`);
}
