import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { RequireAuth } from "@/components/layout/RequireAuth";
import { isAuthenticated, loginWithPassword, logout } from "@/lib/auth";
import { LoginPage } from "@/pages/LoginPage";

describe("LoginPage", () => {
  beforeEach(() => logout());

  it("redirects private routes to login when no session exists", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<div>Login requerido</div>} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<div>Panel privado</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Login requerido")).toBeInTheDocument();
  });

  it("shows an error when credentials are wrong", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Usuario"), "admin");
    await user.type(screen.getByLabelText("Contraseña"), "mal");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      screen.getByText("Usuario o contraseña incorrectos."),
    ).toBeInTheDocument();
    expect(isAuthenticated()).toBe(false);
  });

  it("logs in with fixed credentials and keeps the session", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/login", state: { from: "/settings" } }]}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/settings" element={<div>Panel privado</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Usuario"), "admin");
    await user.type(screen.getByLabelText("Contraseña"), "Tatodobajocontrol");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(screen.getByText("Panel privado")).toBeInTheDocument();
    expect(isAuthenticated()).toBe(true);
  });

  it("allows private routes after refreshing with an active local session", () => {
    expect(loginWithPassword("admin", "Tatodobajocontrol")).toBe(true);

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<div>Login requerido</div>} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<div>Panel privado</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Panel privado")).toBeInTheDocument();
  });
});
