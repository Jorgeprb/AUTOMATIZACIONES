import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "@/components/layout/TopBar";
import { isAuthenticated, loginWithPassword, logout } from "@/lib/auth";

vi.mock("@/hooks/useActiveClinic", () => ({
  useActiveClinic: () => ({
    clinics: [],
    activeClinic: null,
    activeClinicId: null,
    setActiveClinicId: () => undefined,
    isLoading: false,
  }),
}));

describe("TopBar", () => {
  beforeEach(() => logout());

  it("closes the local session from the layout", async () => {
    const user = userEvent.setup();
    expect(loginWithPassword("admin", "Tatodobajocontrol")).toBe(true);

    render(
      <MemoryRouter>
        <TopBar onOpenMenu={() => undefined} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: /cerrar sesión/i }));

    expect(isAuthenticated()).toBe(false);
  });
});
