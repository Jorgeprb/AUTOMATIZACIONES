export type PortalMode = "admin" | "client";

export const portalMode: PortalMode =
  import.meta.env.VITE_PORTAL_MODE === "client" ? "client" : "admin";
export const isClientPortal = portalMode === "client";
export const isAdminPortal = portalMode === "admin";
export const adminPortalUrl =
  (import.meta.env.VITE_ADMIN_PORTAL_URL || "https://admin.autogal.es").replace(/\/+$/, "");
export const clientPortalUrl =
  (import.meta.env.VITE_CLIENT_PORTAL_URL || "https://client.autogal.es").replace(/\/+$/, "");
