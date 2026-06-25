import { apiRequest, toQuery } from "@/api/client";
import type { Page } from "@/schemas/api";
import type {
  PhoneNumber,
  PhoneNumberPayload,
} from "@/schemas/phoneNumber";

export function listPhoneNumbers(
  clinicId: string,
  isActive?: boolean,
): Promise<Page<PhoneNumber>> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/phone-numbers${toQuery({
      page: 1,
      page_size: 100,
      is_active: isActive,
    })}`,
  );
}

export function createPhoneNumber(
  clinicId: string,
  payload: PhoneNumberPayload,
): Promise<PhoneNumber> {
  return apiRequest(`/api/admin/clinics/${clinicId}/phone-numbers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePhoneNumber(
  clinicId: string,
  phoneNumberId: string,
  payload: Partial<PhoneNumberPayload>,
): Promise<PhoneNumber> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/phone-numbers/${phoneNumberId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deletePhoneNumber(
  clinicId: string,
  phoneNumberId: string,
): Promise<{ id: string }> {
  return apiRequest(
    `/api/admin/clinics/${clinicId}/phone-numbers/${phoneNumberId}`,
    { method: "DELETE" },
  );
}
