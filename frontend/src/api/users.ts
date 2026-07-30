import { apiRequest } from "@/api/client";

export type PortalRole = "super_admin" | "clinic_admin" | "operator" | "read_only";
export type PortalPhone = {
  id: string;
  phone_number: string;
  label: string;
  is_active: boolean;
};
export type PortalPendingProvisioning = {
  id: string;
  status: string;
  quantity: number;
  created_at: string;
};
export type PortalMembership = {
  clinic_id: string;
  clinic_name: string;
  role: PortalRole;
  phone_numbers: PortalPhone[];
  pending_provisioning: PortalPendingProvisioning[];
};
export type PortalUser = {
  id: string;
  username: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  auth_provider: string;
  role: PortalRole;
  is_active: boolean;
  google_connected: boolean;
  memberships: PortalMembership[];
};
export type PortalUserPayload = {
  email: string;
  display_name: string;
  role: PortalRole;
  clinic_ids: string[];
  temporary_password?: string | null;
  is_active: boolean;
};

export const listPortalUsers = () => apiRequest<PortalUser[]>("/api/admin/users");
export const createPortalUser = (payload: PortalUserPayload) =>
  apiRequest<PortalUser>("/api/admin/users", { method: "POST", body: JSON.stringify(payload) });
export const updatePortalUser = (userId: string, payload: Partial<PortalUserPayload> & { unlink_google?: boolean }) =>
  apiRequest<PortalUser>(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const deletePortalUser = (userId: string) =>
  apiRequest<void>(`/api/admin/users/${userId}`, { method: "DELETE" });
