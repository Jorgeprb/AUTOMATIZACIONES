import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "@/components/layout/TopBar";
import { logout } from "@/lib/auth";

vi.mock("@/lib/auth", () => ({ logout: vi.fn().mockResolvedValue(undefined) }));
vi.mock("@/hooks/useActiveClinic", () => ({
  useActiveClinic: () => ({
    clinics: [], activeClinic: null, activeClinicId: null,
    setActiveClinicId: () => undefined, isLoading: false,
  }),
}));

describe("TopBar", () => {
  beforeEach(() => vi.clearAllMocks());

  it("revokes the server session from the layout", async () => {
    const user = userEvent.setup();
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><TopBar onOpenMenu={() => undefined} /></MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(screen.getByRole("button", { name: /cerrar sesión/i }));
    expect(logout).toHaveBeenCalledOnce();
  });
});
