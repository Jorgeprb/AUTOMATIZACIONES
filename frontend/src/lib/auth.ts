import { apiRequest } from "@/api/client";

export type AdminIdentity = {
  user_id?: string | null;
  username: string;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  role: "super_admin" | "clinic_admin" | "operator" | "read_only";
  clinic_ids: string[];
  must_change_password?: boolean;
  is_super_admin?: boolean;
};

export function getCurrentAdmin(): Promise<AdminIdentity> {
  return apiRequest<AdminIdentity>("/auth/me");
}

export function loginWithPassword(
  username: string,
  password: string,
): Promise<AdminIdentity> {
  return apiRequest<AdminIdentity>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/logout", { method: "POST" });
}
