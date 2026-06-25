import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type { Service } from "@/schemas/domain";
import type { ServicePayload } from "@/schemas/service";

export function listServices(
  clinicId: string,
  isActive?: boolean,
): Promise<Page<Service>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/services${toQuery({
      page: 1,
      page_size: 100,
      is_active: isActive,
    })}`,
  );
}

export function createService(
  clinicId: string,
  payload: ServicePayload,
): Promise<Service> {
  return apiRequest(`/api/admin/clinics/${clinicId}/services`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateService(
  clinicId: string,
  serviceId: string,
  payload: Partial<ServicePayload>,
): Promise<Service> {
  return apiRequest(`/api/admin/clinics/${clinicId}/services/${serviceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteService(
  clinicId: string,
  serviceId: string,
): Promise<{ id: string }> {
  return apiRequest(`/api/admin/clinics/${clinicId}/services/${serviceId}`, {
    method: "DELETE",
  });
}
