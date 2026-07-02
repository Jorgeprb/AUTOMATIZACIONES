import type { ApiErrorPayload, HealthResponse } from "@/schemas/api";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
  .replace(/\/+$/, "");
const adminApiKey = import.meta.env.VITE_ADMIN_API_KEY || "";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function errorMessage(payload: ApiErrorPayload | null, fallback: string): string {
  if (!payload?.detail) return fallback;
  if (typeof payload.detail === "string") return payload.detail;
  const messages = payload.detail
    .map((item) => item.msg)
    .filter((item): item is string => Boolean(item));
  return messages.length ? messages.join(". ") : fallback;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (path.startsWith("/api/admin")) {
    headers.set("X-Admin-API-Key", adminApiKey);
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers,
    });
  } catch {
    throw new ApiError(
      "No se pudo conectar con el backend. Comprueba VITE_API_BASE_URL.",
      0,
    );
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | ApiErrorPayload
      | null;
    throw new ApiError(
      errorMessage(payload, `La API respondió con ${response.status}.`),
      response.status,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiBlobRequest(
  path: string,
  init: RequestInit = {},
): Promise<Blob> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (path.startsWith("/api/admin")) {
    headers.set("X-Admin-API-Key", adminApiKey);
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers,
    });
  } catch {
    throw new ApiError(
      "No se pudo conectar con el backend. Comprueba VITE_API_BASE_URL.",
      0,
    );
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | ApiErrorPayload
      | null;
    throw new ApiError(
      errorMessage(payload, `La API respondió con ${response.status}.`),
      response.status,
    );
  }
  return response.blob();
}

export function toQuery(
  values: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const result = search.toString();
  return result ? `?${result}` : "";
}

export function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health/ready");
}

export const apiConfig = {
  baseUrl: apiBaseUrl,
  adminApiKey,
  hasAdminKey: Boolean(adminApiKey),
};
