import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "@/api/client";

describe("apiRequest", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("exposes backend errors with their HTTP status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Calendario no autorizado" }), {
          status: 401,
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
  });

  it("returns a clear network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(apiRequest("/health/ready")).rejects.toMatchObject({
      status: 0,
    });
  });
});
