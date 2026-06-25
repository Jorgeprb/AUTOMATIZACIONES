import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import {
  getCalendarStatus,
  getGoogleOAuthDiagnostics,
  listCalendars,
} from "@/api/calendar";
import { listAppointments } from "@/api/appointments";
import { listServices } from "@/api/services";
import { listWorkers } from "@/api/workers";
import { CalendarPage } from "@/pages/CalendarPage";

vi.mock("@/hooks/useClinicRoute", () => ({
  useClinicRoute: () => "clinic-1",
}));

vi.mock("@/api/calendar", () => ({
  createWorkerCalendar: vi.fn(),
  getCalendarStatus: vi.fn(),
  getGoogleOAuthDiagnostics: vi.fn(),
  getGoogleOAuthStartUrl: vi.fn(),
  linkWorkerCalendar: vi.fn(),
  listCalendars: vi.fn(),
  testWorkerFreeBusy: vi.fn(),
}));

vi.mock("@/api/appointments", () => ({
  cancelAppointment: vi.fn(),
  listAppointments: vi.fn(),
}));

vi.mock("@/api/services", () => ({
  listServices: vi.fn(),
}));

vi.mock("@/api/workers", () => ({
  listWorkers: vi.fn(),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CalendarPage Google OAuth diagnostics", () => {
  it("disables Google connect and shows .env fixes when OAuth is misconfigured", async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      clinic_id: "clinic-1",
      connected: false,
      needs_reauthorization: false,
      account_email: null,
      workers_total: 2,
      workers_linked: 0,
    });
    vi.mocked(getGoogleOAuthDiagnostics).mockResolvedValue({
      clinic_id: "clinic-1",
      configured: false,
      can_start_oauth: false,
      connected: false,
      needs_reauthorization: false,
      account_email: null,
      redirect_uri: "https://replace-me.ngrok-free.app/auth/google/callback",
      public_base_url: "https://replace-me.ngrok-free.app",
      frontend_base_url: "http://localhost:5173",
      issues: [
        {
          variable: "GOOGLE_TOKEN_ENCRYPTION_KEY",
          severity: "error",
          message: "GOOGLE_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.",
          help: "Generate a real Fernet key.",
        },
      ],
    });
    vi.mocked(listWorkers).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      pages: 0,
    });
    vi.mocked(listServices).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      pages: 0,
    });
    vi.mocked(listAppointments).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
      pages: 0,
    });

    renderPage();

    expect(await screen.findByText("Google OAuth mal configurado")).toBeInTheDocument();
    expect(screen.getAllByText("GOOGLE_TOKEN_ENCRYPTION_KEY").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByRole("button", { name: /Conectar Google Calendar/ }),
    ).toBeDisabled();
    expect(listCalendars).not.toHaveBeenCalled();
  });
});
