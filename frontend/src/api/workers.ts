import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type { Worker } from "@/schemas/domain";
import type { WorkerPayload } from "@/schemas/worker";

export function listWorkers(
  clinicId: string,
  isActive?: boolean,
): Promise<Page<Worker>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/workers${toQuery({
      page: 1,
      page_size: 100,
      is_active: isActive,
    })}`,
  );
}

export function createWorker(
  clinicId: string,
  payload: WorkerPayload,
): Promise<Worker> {
  return apiRequest(`/api/admin/clinics/${clinicId}/workers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateWorker(
  clinicId: string,
  workerId: string,
  payload: Partial<WorkerPayload>,
): Promise<Worker> {
  return apiRequest(`/api/admin/clinics/${clinicId}/workers/${workerId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteWorker(
  clinicId: string,
  workerId: string,
): Promise<{ id: string }> {
  return apiRequest(`/api/admin/clinics/${clinicId}/workers/${workerId}`, {
    method: "DELETE",
  });
}
