import { apiRequest } from "@/api/client";
import type { ClinicDashboard, SetupStatus } from "@/schemas/domain";

export function getClinicDashboard(
  clinicId: string,
): Promise<ClinicDashboard> {
  return apiRequest(`/api/admin/clinics/${clinicId}/dashboard`);
}

export function getSetupStatus(clinicId: string): Promise<SetupStatus> {
  return apiRequest(`/api/admin/clinics/${clinicId}/setup-status`);
}
