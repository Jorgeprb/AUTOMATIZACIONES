import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type { Clinic, ClinicPayload } from "@/schemas/clinic";

export function listClinics(params: {
  page?: number;
  pageSize?: number;
  isActive?: boolean;
} = {}): Promise<Page<Clinic>> {
  return apiRequest(
    `/api/admin/clinics${toQuery({
      page: params.page ?? 1,
      page_size: params.pageSize ?? 100,
      is_active: params.isActive,
    })}`,
  );
}

export async function listAllClinics(): Promise<Clinic[]> {
  const first = await listClinics({ page: 1, pageSize: 100 });
  if (first.pages <= 1) return first.items;
  const remaining = await Promise.all(
    Array.from({ length: first.pages - 1 }, (_, index) =>
      listClinics({ page: index + 2, pageSize: 100 }),
    ),
  );
  return [first, ...remaining].flatMap((page) => page.items);
}

export function getClinic(clinicId: string): Promise<Clinic> {
  return apiRequest(`/api/admin/clinics/${clinicId}`);
}

export function createClinic(payload: ClinicPayload): Promise<Clinic> {
  return apiRequest("/api/admin/clinics", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateClinic(
  clinicId: string,
  payload: Partial<ClinicPayload>,
): Promise<Clinic> {
  return apiRequest(`/api/admin/clinics/${clinicId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteClinic(clinicId: string): Promise<{ id: string }> {
  return apiRequest(`/api/admin/clinics/${clinicId}`, {
    method: "DELETE",
  });
}
