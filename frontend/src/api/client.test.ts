import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "@/api/client";

describe("apiRequest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("exposes backend errors without closing a still valid session", async () => {
    const unauthorized = vi.fn();
    window.addEventListener("autogal:unauthorized", unauthorized);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: "Calendario no autorizado" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ username: "cliente" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );

    await expect(apiRequest("/api/admin/clinics")).rejects.toEqual(
      expect.objectContaining<ApiError>({
        message: "Calendario no autorizado",
        name: "ApiError",
        status: 401,
      }),
    );
    expect(unauthorized).not.toHaveBeenCalled();
    window.removeEventListener("autogal:unauthorized", unauthorized);
  });

  it("notifies the shell when the authentication probe also fails", async () => {
    const unauthorized = vi.fn();
    window.addEventListener("autogal:unauthorized", unauthorized);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(null, { status: 401 }))
        .mockResolvedValueOnce(new Response(null, { status: 401 })),
    );

    await expect(apiRequest("/api/admin/clinics")).rejects.toMatchObject({
      status: 401,
    });
    expect(unauthorized).toHaveBeenCalledTimes(1);
    window.removeEventListener("autogal:unauthorized", unauthorized);
  });

  it("returns a clear network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(apiRequest("/health/ready")).rejects.toMatchObject({
      status: 0,
    });
  });
});
