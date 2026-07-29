import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { getCurrentAdmin, loginWithPassword } from "@/lib/auth";
import { LoginPage } from "@/pages/LoginPage";

vi.mock("@/lib/auth", () => ({
  getCurrentAdmin: vi.fn(),
  loginWithPassword: vi.fn(),
  logout: vi.fn(),
}));

const identity = { username: "admin", role: "super_admin" as const, clinic_ids: [] };

function renderWithProviders(ui: React.ReactNode, initialEntries = ["/"]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCurrentAdmin).mockRejectedValue(new ApiError("Unauthorized", 401));
  });

  it("redirects private routes to login when no server session exists", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<div>Login requerido</div>} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<div>Panel privado</div>} />
        </Route>
      </Routes>,
    );
    expect(await screen.findByText("Login requerido")).toBeInTheDocument();
  });

  it("shows the backend error when credentials are wrong", async () => {
    vi.mocked(loginWithPassword).mockRejectedValue(
      new ApiError("Usuario o contraseña incorrectos.", 401),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <Routes><Route path="/login" element={<LoginPage />} /></Routes>,
      ["/login"],
    );
    await user.type(screen.getByLabelText("Usuario o email"), "admin");
    await user.type(screen.getByLabelText("Contraseña"), "mal");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Usuario o contraseña incorrectos.",
    );
  });

  it("stores the authenticated identity in React Query and redirects", async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(identity);
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Panel privado</div>} />
      </Routes>,
      ["/login"],
    );
    await user.type(screen.getByLabelText("Usuario o email"), "admin");
    await user.type(screen.getByLabelText("Contraseña"), "Test-only-password-123!");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("Panel privado")).toBeInTheDocument();
    expect(loginWithPassword).toHaveBeenCalledWith("admin", "Test-only-password-123!");
  });

  it("allows private routes when the server session is active", async () => {
    vi.mocked(getCurrentAdmin).mockResolvedValue(identity);
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<div>Login requerido</div>} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<div>Panel privado</div>} />
        </Route>
      </Routes>,
    );
    await waitFor(() => expect(screen.getByText("Panel privado")).toBeInTheDocument());
  });
});
