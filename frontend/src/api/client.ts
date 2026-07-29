import type { ApiErrorPayload, HealthResponse } from "@/schemas/api";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
  .replace(/\/+$/, "");
const defaultTimeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS || 20000);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
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

export function cookieValue(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

function isUnsafeMethod(method: string): boolean {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs = defaultTimeoutMs,
): Promise<Response> {
  const controller = new AbortController();
  const externalSignal = init.signal;
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortFromExternal = () => controller.abort();
  externalSignal?.addEventListener("abort", abortFromExternal, { once: true });
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}


let authProbe: Promise<boolean> | null = null;

async function sessionIsStillValid(): Promise<boolean> {
  if (!authProbe) {
    authProbe = fetchWithTimeout(`${apiBaseUrl}/auth/me`, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then((response) => response.status !== 401)
      .catch(() => true)
      .finally(() => {
        authProbe = null;
      });
  }
  return authProbe;
}

async function handleUnauthorized(path: string): Promise<void> {
  if (path === "/auth/login" || path.startsWith("/auth/google")) return;
  const invalid = path === "/auth/me" || !(await sessionIsStillValid());
  if (invalid) window.dispatchEvent(new CustomEvent("autogal:unauthorized"));
}

async function checkedResponse(
  path: string,
  init: RequestInit,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const method = init.method || "GET";
  if (isUnsafeMethod(method)) {
    const csrfToken = cookieValue("autogal_admin_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }

  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
    if (response.status === 401) {
      await handleUnauthorized(path);
    }
    return response;
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    throw new ApiError(
      aborted
        ? "La petición superó el tiempo máximo de espera."
        : "No se pudo conectar con el backend. Comprueba VITE_API_BASE_URL.",
      0,
    );
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await checkedResponse(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | ApiErrorPayload
      | null;
    throw new ApiError(
      errorMessage(payload, `La API respondió con ${response.status}.`),
      response.status,
      response.headers.get("X-Request-ID") || undefined,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiBlobRequest(
  path: string,
  init: RequestInit = {},
): Promise<Blob> {
  const response = await checkedResponse(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | ApiErrorPayload
      | null;
    throw new ApiError(
      errorMessage(payload, `La API respondió con ${response.status}.`),
      response.status,
      response.headers.get("X-Request-ID") || undefined,
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
  timeoutMs: defaultTimeoutMs,
};
